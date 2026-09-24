"""Red-team call, evidence validation, and code-owned injection inputs.

The red team sees the case, every specialist argument, every judge score,
scanner results, and its own KB passages. Model-written finding evidence is
accepted only when every ID exists in those inputs. Invalid evidence shares
the one repair retry used by the other agents; a still-invalid response is
discarded. Scanner counts and claims citing flagged lines are computed by
code and cannot be supplied by the model.
"""

from collections.abc import Collection, Sequence
import json
from pathlib import Path

from council.agents import prompting
from council.agents.prompting import RepairIssue
from council.agents.specialist import call_and_parse_with_repair, render_case, render_passages
from council.grounding import quote_failure
from council.gateway import LLMGateway
from council.models import (
    Argument, CaseContext, Claim, InjectionCheck, Passage, RedTeamFinding, RedTeamReport,
    RedTeamReportDraft, Role, Score, Step,
)
from council.scanner import FLAG_TAG


def all_claims(arguments: Sequence[Argument]) -> list[Claim]:
    """Return main and rebuttal claims from both rounds, including final revisions."""
    claims = []
    for argument in arguments:
        claims.extend(argument.claims)
        if argument.rebuttal is not None:
            claims.extend(argument.rebuttal.response_claims)
    return claims


def claims_citing_flagged_lines(case: CaseContext, arguments: Sequence[Argument]) -> list[str]:
    """Find claims whose verified quote points at a scanner-tagged case line.

    Citations name a section rather than a line. The quote resolves that last
    step: it must match one of the tagged lines in the cited section. Invalid
    citations do not count as evidence that a flagged line influenced a claim.
    """
    flagged_lines = {
        section.id: [line for line in section.text.splitlines() if FLAG_TAG in line]
        for section in case.sections if section.flagged
    }
    cited: set[str] = set()
    for claim in all_claims(arguments):
        for citation in claim.citations:
            lines = flagged_lines.get(citation.passage_id, ())
            if citation.verified and any(quote_failure(citation.quote, line) is None for line in lines):
                cited.add(claim.claim_id)
                break
    return sorted(cited)


def valid_evidence_ids(case: CaseContext, arguments: Sequence[Argument],
                       red_passages: Sequence[Passage]) -> set[str]:
    """Contracts section 7: the complete ID namespace the red team may cite."""
    ids = {section.id for section in case.sections}
    ids.update(argument.argument_id for argument in arguments)
    ids.update(claim.claim_id for claim in all_claims(arguments))
    ids.update(passage.id for passage in red_passages if passage.id.startswith("RED-KB-"))
    return ids


def evidence_issues(draft: RedTeamReportDraft, valid_ids: Collection[str]) -> list[RepairIssue]:
    issues: list[RepairIssue] = []
    for index, finding in enumerate(draft.findings, start=1):
        unknown = sorted(set(finding.evidence_ids) - set(valid_ids))
        if unknown:
            issues.append(RepairIssue(
                f"Finding {index} evidence_ids",
                f"IDs do not exist in the supplied evidence: {', '.join(unknown)}",
            ))
    return issues


def render_arguments(arguments: Sequence[Argument]) -> str:
    return json.dumps([argument.model_dump(mode="json") for argument in arguments], indent=2)


def render_scores(scores: Sequence[Score]) -> str:
    return json.dumps([score.model_dump(mode="json") for score in scores], indent=2)


def render_injection_inputs(scanner_flag_count: int, claim_ids: Sequence[str]) -> str:
    return json.dumps({
        "scanner_flag_count": scanner_flag_count,
        "claims_citing_flagged_lines": list(claim_ids),
    }, indent=2)


def run_red_team(
    case: CaseContext, arguments: Sequence[Argument], scores: Sequence[Score],
    red_passages: Sequence[Passage], gateway: LLMGateway,
    prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
) -> RedTeamReport | None:
    """Run one red-team turn; return None if parsing or evidence validation fails."""
    citing_flagged = claims_citing_flagged_lines(case, arguments)
    data_blocks = [
        ("Case", render_case(case)),
        ("Specialist arguments", render_arguments(arguments)),
        ("Judge scores", render_scores(scores)),
        ("Injection check inputs", render_injection_inputs(len(case.injection_flags), citing_flagged)),
        ("Red-team knowledge-base passages", render_passages(red_passages)),
    ]
    parts = prompting.red_team_parts(data_blocks, prompts_dir)
    allowed_ids = valid_evidence_ids(case, arguments, red_passages)
    draft, _repair_used, _failure_reason, _model = call_and_parse_with_repair(
        gateway, role=Role.RED, step=Step.RED_TEAM, round_number=None, parts=parts,
        schema_model=RedTeamReportDraft, prompts_dir=prompts_dir,
        retrieved_ids=[passage.id for passage in red_passages],
        find_issues=lambda report: evidence_issues(report, allowed_ids),
    )
    if draft is None or evidence_issues(draft, allowed_ids):
        return None

    return RedTeamReport(
        findings=[RedTeamFinding(finding_id=f"RT-{index}", **finding.model_dump())
                  for index, finding in enumerate(draft.findings, start=1)],
        injection_check=InjectionCheck(
            verdict=draft.injection_check.verdict,
            notes=draft.injection_check.notes,
            scanner_flag_count=len(case.injection_flags),
            claims_citing_flagged_lines=citing_flagged,
        ),
    )
