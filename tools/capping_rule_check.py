"""Compare the groundedness capping rule with committed and candidate prompts.

This is a deliberately small live-model check, not a council run. It sends the
same synthetic argument to JUDGE_A twice through LLMGateway. The baseline
rubric and judge instructions are read from Git HEAD; the candidate copies are
read from a directory supplied on the command line.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

from council.agents import judge as judge_agent
from council.agents import prompting
from council.agents.specialist import parse_draft
from council.budget import Budget
from council.config import load_config
from council.gateway import GatewayResult, LLMGateway
from council.models import (
    Argument,
    CaseContext,
    CaseSection,
    Citation,
    Claim,
    Role,
    ScoreDraft,
    Step,
)
from council.providers.factory import build_providers
from council.trace import TraceWriter


REPO_ROOT = Path(__file__).resolve().parents[1]
CLAIM_ID = "R1-PHYS-C1"


@dataclass(frozen=True)
class CheckedResponse:
    label: str
    result: GatewayResult
    parsed: ScoreDraft | None
    parse_error: str | None


def committed_prompt(filename: str) -> str:
    """Read a prompt exactly as committed at HEAD, independent of worktree edits."""
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"HEAD:prompts/{filename}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def candidate_prompt(candidate_dir: Path, filename: str) -> str:
    path = candidate_dir / filename
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except OSError as error:
        raise SystemExit(f"Cannot read candidate prompt: {path}") from error
    if not text:
        raise SystemExit(f"Candidate prompt is empty: {path}")
    return text


def fixture() -> tuple[CaseContext, Argument, dict[str, str]]:
    """Create a verified quotation that does not support its claim's assertion."""
    case = CaseContext(
        case_id="synthetic-grounding-cap-check",
        source_file="synthetic/in-memory.md",
        case_hash="a" * 64,
        title="Synthetic grounding cap check",
        sections=[CaseSection(
            id="CASE-profile",
            heading="Patient Profile",
            text="Synthetic adult considering an elective intervention.",
            flagged=False,
            flag_reasons=[],
        )],
        missing_sections=[],
        injection_flags=[],
    )
    passage_id = "PHYS-KB-TEST-01"
    quote = "In stable adults, the intervention shortened hospital stay by one day."
    passage = (
        f"{quote} The study did not evaluate mortality, stroke, or renal outcomes."
    )
    argument = Argument(
        argument_id="R1-PHYS",
        role=Role.PHYS,
        round=1,
        stance="for",
        summary="The intervention improves major clinical outcomes.",
        claims=[Claim(
            claim_id=CLAIM_ID,
            text="The intervention reduces 30-day mortality and stroke.",
            citations=[Citation(
                passage_id=passage_id,
                quote=quote,
                source_type="kb",
                verified=True,
                verify_note="",
            )],
            grounding_status="grounded",
        )],
        conditions=[],
        uncertainties=[],
        rebuttal=None,
        revisions=None,
        stance_changed=False,
        retrieved_passage_ids=[passage_id],
        repair_used=False,
        status="ok",
        failure_reason=None,
    )
    return case, argument, {passage_id: passage}


def user_message() -> str:
    """Assemble the fixture exactly like the current one-argument judge path."""
    case, argument, passage_sources = fixture()
    sources = {section.id: section.text for section in case.sections}
    sources.update(passage_sources)
    cited_ids = set(judge_agent.cited_passage_ids([argument]))
    uncited_case = case.model_copy(update={
        "sections": [section for section in case.sections if section.id not in cited_ids],
    })
    blocks = [
        ("Case sections not repeated below", judge_agent.render_case(uncited_case)),
        ("Cited sources", judge_agent.render_shared_sources([argument], sources)),
        (argument.argument_id, judge_agent.render_argument(argument)),
    ]
    return prompting.render_user(prompting.user_data(blocks), ScoreDraft)


def system_message(rubric: str, judge: str) -> str:
    return prompting.join_sections([rubric, judge])


def call_judge(gateway: LLMGateway, label: str, system: str, user: str) -> CheckedResponse:
    result = gateway.call(
        role=Role.JUDGE_A,
        step=Step.JUDGE,
        round_number=1,
        system=system,
        user=user,
        retrieved_passage_ids=[],
    )
    parsed, parse_error = parse_draft(result.raw_output, ScoreDraft)
    return CheckedResponse(label, result, parsed, parse_error)


def side_by_side(left: CheckedResponse, right: CheckedResponse, width: int = 72) -> str:
    """Render both complete raw responses in readable terminal columns."""
    def wrapped_lines(raw: str) -> list[str]:
        lines = [
            wrapped
            for original in raw.splitlines() or [""]
            for wrapped in (textwrap.wrap(original, width=width) or [""])
        ]
        return lines or [""]

    left_lines = wrapped_lines(left.result.raw_output)
    right_lines = wrapped_lines(right.result.raw_output)
    rows = [f"{left.label:<{width}} | {right.label}", f"{'-' * width}-+-{'-' * width}"]
    for index in range(max(len(left_lines), len(right_lines))):
        left_text = left_lines[index] if index < len(left_lines) else ""
        right_text = right_lines[index] if index < len(right_lines) else ""
        rows.append(f"{left_text:<{width}} | {right_text}")
    return "\n".join(rows)


def parsed_summary(response: CheckedResponse) -> str:
    if response.parsed is None:
        return f"{response.label}: response did not match ScoreDraft: {response.parse_error}"
    score = response.parsed
    flagged = next(
        (item for item in score.untraceable_claims if item.claim_id == CLAIM_ID),
        None,
    )
    return "\n".join([
        response.label,
        f"  model: {response.result.model}",
        f"  groundedness: {score.groundedness} (cap obeyed: {score.groundedness <= 2})",
        f"  groundedness justification: {score.justification.get('groundedness', '(missing)')}",
        f"  {CLAIM_ID} appears in untraceable_claims: {flagged is not None}",
        f"  untraceable reason: {flagged.reason if flagged is not None else '(not listed)'}",
        f"  tokens: {response.result.tokens_in} in, {response.result.tokens_out} out",
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare JUDGE_A's groundedness cap using committed and candidate prompts.",
    )
    parser.add_argument(
        "candidate_prompts",
        type=Path,
        help="Directory containing the candidate judge.md and rubric.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate_dir = args.candidate_prompts.resolve()
    current_system = system_message(
        committed_prompt("rubric.md"), committed_prompt("judge.md"),
    )
    candidate_system = system_message(
        candidate_prompt(candidate_dir, "rubric.md"),
        candidate_prompt(candidate_dir, "judge.md"),
    )
    user = user_message()
    config = load_config(REPO_ROOT / "config.yaml")

    with tempfile.TemporaryDirectory(prefix="council-capping-rule-") as temp_dir:
        trace = TraceWriter(Path(temp_dir) / "trace.jsonl", "targeted-capping-rule-check")
        gateway = LLMGateway(config, Budget(config.budget), trace, build_providers(config))
        current = call_judge(gateway, "CURRENT COMMITTED", current_system, user)
        candidate = call_judge(gateway, "CANDIDATE TRIMMED", candidate_system, user)

    print("\nFULL RAW RESPONSES\n")
    print(side_by_side(current, candidate))
    print("\nPARSED COMPARISON\n")
    print(parsed_summary(current))
    print()
    print(parsed_summary(candidate))


if __name__ == "__main__":
    main()
