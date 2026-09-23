"""Command-line run workflow and human clinical sign-off gate."""

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from council.budget import Budget
from council.config import ConfigError, load_config
from council.gateway import LLMGateway
from council.ingest import IngestError, ingest_case
from council.kb import KBError, KnowledgeBase, load_kb
from council.models import (
    CaseContext, Config, Decision, EventType, HumanDecision, Report, Role, RunBundle, Source,
    SourceType, Step, TraceEvent,
)
from council.orchestrator import CouncilRun, run_council
from council.providers.base import Provider
from council.providers.factory import ProviderConfigurationError, build_providers
from council.trace import TraceWriteError, TraceWriter

Input = Callable[[str], str]
Output = Callable[[str], None]
Clock = Callable[[], datetime]


def new_run_id(case_id: str, now: datetime) -> str:
    """Create the contracted timestamped run ID from a safe case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", case_id.casefold()).strip("-") or "case"
    return f"run-{now:%Y%m%d-%H%M%S}-{slug}"


def collect_sources(case: CaseContext, kb: KnowledgeBase, result: CouncilRun) -> dict[str, Source]:
    """Bundle every available case/KB source cited by a claim or red-team finding."""
    if result.report.case_id != case.case_id:
        raise ValueError("report and case IDs do not match")
    case_sections = {section.id: section for section in case.sections}
    passages = {passage.id: passage for items in kb.passages.values() for passage in items}
    wanted = {
        citation.passage_id
        for argument in result.arguments
        for claim in [*argument.claims,
                      *(argument.rebuttal.response_claims if argument.rebuttal is not None else [])]
        for citation in claim.citations
    }
    if result.red_team is not None:
        wanted.update(evidence_id for finding in result.red_team.findings
                      for evidence_id in finding.evidence_ids)
    sources: dict[str, Source] = {}
    for source_id in sorted(wanted):
        if source_id in case_sections:
            section = case_sections[source_id]
            sources[source_id] = Source(
                source_type=SourceType.CASE, source_title=section.heading, text=section.text,
            )
        elif source_id in passages:
            passage = passages[source_id]
            sources[source_id] = Source(
                source_type=SourceType.KB, source_title=passage.source_title, text=passage.text,
            )
    return sources


def report_markdown(report: Report) -> str:
    """Render the report people inspect before the human gate."""
    lines = [
        f"# Council report: {report.run_id}", "", f"> {report.disclaimer}", "",
        f"- Status: **{report.status.value}**",
        f"- Recommendation: **{report.recommendation.value if report.recommendation else 'none'}**",
        f"- Incomplete reasons: {', '.join(report.incomplete_reasons) or 'none'}",
        f"- Failed turns: {', '.join(report.failed_turns) or 'none'}", "",
        "## Narrative", "", report.narrative or "No chair narrative is available.", "",
        "## Recommendation evidence", "",
        f"- Basis: {', '.join(report.recommendation_basis) or 'none'}",
        f"- Strongest for: {', '.join(report.strongest_for) or 'none'}",
        f"- Strongest against: {', '.join(report.strongest_against) or 'none'}", "",
        "## Required actions", "",
    ]
    lines.extend(f"- {action.text} ({', '.join(action.source_ids)})"
                 for action in report.required_actions)
    if not report.required_actions:
        lines.append("- None")
    lines.extend(["", "## Red team", ""])
    lines.extend(
        f"- [{finding.finding_id}] {finding.severity.value} {finding.category.value}: "
        f"{finding.description} Evidence: {', '.join(finding.evidence_ids)}"
        for finding in report.red_team_findings
    )
    if not report.red_team_findings:
        lines.append("- No findings recorded")
    lines.extend([
        "", "## Injection check", "", f"- Verdict: **{report.injection_check.verdict.value}**",
        f"- Scanner flags: {report.injection_check.scanner_flag_count}",
        f"- Claims citing flagged lines: "
        f"{', '.join(report.injection_check.claims_citing_flagged_lines) or 'none'}",
        f"- Notes: {report.injection_check.notes}", "", "## Human decision", "",
    ])
    if report.human_decision is None:
        lines.append("Pending human clinical sign-off.")
    else:
        decision = report.human_decision
        lines.extend([
            f"- Decision: **{decision.decision.value}**", f"- Reviewer: {decision.reviewer}",
            f"- Decided at: {decision.decided_at.isoformat()}",
            f"- Comment: {decision.comment or 'none'}", f"- Report hash: `{decision.report_hash}`",
        ])
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: object) -> None:
    """Write validated models as stable, readable UTF-8 JSON."""
    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_artifacts(folder: Path, bundle: RunBundle) -> bytes:
    """Write T16's three derived artifacts; TraceWriter owns trace.jsonl."""
    markdown = report_markdown(bundle.report).encode("utf-8")
    write_json(folder / "run.json", bundle)
    write_json(folder / "scorecard.json", bundle.scorecard)
    (folder / "report.md").write_bytes(markdown)
    return markdown


def ask_nonblank(prompt: str, input_fn: Input) -> str:
    while not (value := input_fn(prompt).strip()):
        pass
    return value


def ask_human_decision(run_id: str, report_bytes: bytes, input_fn: Input,
                       now: datetime) -> HumanDecision:
    """Collect approve/reject/comment and bind it to the exact displayed report bytes."""
    choices = {"approve": Decision.APPROVED, "reject": Decision.REJECTED,
               "comment": Decision.COMMENT_ONLY}
    choice = ""
    while choice not in choices:
        choice = input_fn("Decision [approve/reject/comment]: ").strip().casefold()
    comment = ask_nonblank("Comment: ", input_fn) if choice == "comment" else ""
    reviewer = ask_nonblank("Reviewer (fictional name): ", input_fn)
    return HumanDecision(
        run_id=run_id, decision=choices[choice], comment=comment, reviewer=reviewer,
        decided_at=now, report_hash=sha256(report_bytes).hexdigest(),
    )


def build_bundle(run_id: str, created_at: datetime, config: Config, case: CaseContext,
                 kb: KnowledgeBase, result: CouncilRun) -> RunBundle:
    return RunBundle(
        run_id=run_id, case_id=case.case_id, created_at=created_at,
        config_snapshot=config.model_dump(mode="json"), case_context=case,
        retrievals=result.retrievals, arguments=result.arguments, scorecard=result.scorecard,
        red_team=result.red_team, report=result.report, sources=collect_sources(case, kb, result),
    )


def run_command(case_path: Path, config_path: Path, providers: Mapping[str, Provider] | None = None,
                input_fn: Input = input, output_fn: Output = print,
                clock: Clock = lambda: datetime.now(timezone.utc)) -> Path:
    """Run the council, write T16 artifacts, and save the hash-bound human decision.

    `providers=None` is the real CLI's normal path: real adapters are built from
    config (T17's `build_providers`), reading each provider's API key from the
    environment. Callers that need a stand-in (tests, `tools/demo_run.py`) pass an
    explicit mapping instead, which is used exactly as given."""
    config = load_config(config_path)
    resolved_providers = dict(providers) if providers is not None else build_providers(config)
    created_at = clock()
    case = ingest_case(case_path, config)
    run_id = new_run_id(case.case_id, created_at)
    folder = Path(config.paths.runs) / run_id
    folder.mkdir(parents=True, exist_ok=False)
    trace = TraceWriter(folder / "trace.jsonl", run_id)
    kb = load_kb({role: settings.kb for role, settings in config.roles.items()})
    gateway = LLMGateway(config, Budget(config.budget), trace, resolved_providers)
    result = run_council(run_id=run_id, case=case, kb=kb, config=config, gateway=gateway,
                         prompts_dir=config.paths.prompts)
    bundle = build_bundle(run_id, created_at, config, case, kb, result)
    report_bytes = write_artifacts(folder, bundle)
    output_fn(report_bytes.decode("utf-8"))
    decision = ask_human_decision(run_id, report_bytes, input_fn, clock())
    final_report = result.report.model_copy(update={"human_decision": decision})
    bundle = bundle.model_copy(update={"report": final_report})
    trace.write(TraceEvent(
        run_id=run_id, seq=0, timestamp="", step=Step.HUMAN, event_type=EventType.DECISION,
        role=None, round=None, model=None, prompt=None, retrieved_passage_ids=None,
        raw_output=None, parsed_ref=decision.decision.value, tokens_in=None, tokens_out=None,
        latency_ms=None, attempt=1, repair=False,
        budget_tokens_used=gateway.budget_state().tokens_used, error=None,
        finish_reason=None, reasoning=None,
    ))
    write_artifacts(folder, bundle)
    output_fn(f"Saved {decision.decision.value} decision in {folder}")
    return folder


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        prog="python -m council",
        description=("LLM Council: decision support only; requires human clinical sign-off. "
                     "Synthetic data only."),
    )
    subparsers = command_parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="run the council on one synthetic case")
    run.add_argument("case", type=Path)
    run.add_argument("--config", type=Path, default=Path("config.yaml"))
    return command_parser


def main(argv: Sequence[str] | None = None, *, providers: Mapping[str, Provider] | None = None,
         input_fn: Input = input, output_fn: Output = print,
         clock: Clock = lambda: datetime.now(timezone.utc)) -> int:
    """CLI entry point. `providers=None` (the real `python -m council run` invocation)
    builds real adapters from config; tests and tools/demo_run.py inject FakeProvider."""
    command_parser = parser()
    args = command_parser.parse_args(argv)
    if args.command is None:
        command_parser.print_help()
        return 0
    try:
        run_command(args.case, args.config, providers, input_fn, output_fn, clock)
    except (ConfigError, IngestError, KBError, TraceWriteError, OSError, ValueError,
            ProviderConfigurationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
