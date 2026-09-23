"""Chair synthesis and code-side report validation."""

from collections.abc import Collection, Sequence
import json
from pathlib import Path
import re

from council.agents import prompting
from council.agents.prompting import RepairIssue
from council.agents.specialist import call_and_parse_with_repair
from council.gateway import LLMGateway
from council.models import (
    Argument, GroundingStatus, JudgeSummary, PrivacySummary, RedTeamReport, Report,
    ReportDraft, Role, Score, Step,
)
from council.report import bare_report, full_report
from council.scoring import final_arguments

ID_TAG = re.compile(r"\[([^\[\]]+)\]")
SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")


def render_json(items: Sequence[object]) -> str:
    return json.dumps([item.model_dump(mode="json") for item in items], indent=2)  # type: ignore[attr-defined]


def narrative_issues(narrative: str, valid_ids: Collection[str]) -> list[RepairIssue]:
    issues: list[RepairIssue] = []
    sentences = [match.group().strip() for match in SENTENCE.finditer(narrative) if match.group().strip()]
    if not sentences:
        return [RepairIssue("narrative", "must contain at least one sentence ending with a real ID tag")]
    for index, sentence in enumerate(sentences, start=1):
        tags = ID_TAG.findall(sentence)
        ending = re.search(r"(?:\[[^\[\]]+\])+(?:[.!?]+)?$", sentence)
        if ending is None:
            issues.append(RepairIssue(f"narrative sentence {index}", "must end with at least one ID tag"))
        unknown = sorted(set(tags) - set(valid_ids))
        if unknown:
            issues.append(RepairIssue(f"narrative sentence {index}",
                                      f"uses IDs that do not exist: {', '.join(unknown)}"))
    return issues


def chair_issues(draft: ReportDraft, final: Sequence[Argument], red_team: RedTeamReport) -> list[RepairIssue]:
    final_argument_ids = {argument.argument_id for argument in final}
    final_claims = {
        claim.claim_id: claim for argument in final
        for claim in ([*argument.claims, *(argument.rebuttal.response_claims if argument.rebuttal else [])])
    }
    finding_ids = {finding.finding_id for finding in red_team.findings}
    issues: list[RepairIssue] = []

    bad_basis = sorted(set(draft.recommendation_basis) - final_argument_ids)
    if bad_basis:
        issues.append(RepairIssue("recommendation_basis",
                                  f"must use final-round argument IDs only: {', '.join(bad_basis)}"))
    for field_name in ("strongest_for", "strongest_against"):
        ids = getattr(draft, field_name)
        invalid = sorted(id for id in ids if id not in final_claims)
        ungrounded = sorted(id for id in ids if id in final_claims
                            and final_claims[id].grounding_status != GroundingStatus.GROUNDED)
        if invalid:
            issues.append(RepairIssue(field_name,
                                      f"must use final-round claim IDs only: {', '.join(invalid)}"))
        if ungrounded:
            issues.append(RepairIssue(field_name,
                                      f"must use grounded claims only: {', '.join(ungrounded)}"))

    action_ids = set(final_claims) | finding_ids
    for index, action in enumerate(draft.required_actions, start=1):
        invalid = sorted(set(action.source_ids) - action_ids)
        if invalid:
            issues.append(RepairIssue(f"required_actions {index} source_ids",
                                      f"must use final claim or red-team finding IDs: {', '.join(invalid)}"))

    expected_roles = {argument.role for argument in final}
    actual_roles = set(draft.role_notes)
    if actual_roles != expected_roles:
        missing = sorted(role.value for role in expected_roles - actual_roles)
        extra = sorted(role.value for role in actual_roles - expected_roles)
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if extra:
            detail.append("not a non-failed final specialist: " + ", ".join(extra))
        issues.append(RepairIssue("role_notes", "; ".join(detail)))

    narrative_ids = final_argument_ids | set(final_claims) | finding_ids
    issues.extend(narrative_issues(draft.narrative, narrative_ids))
    return issues


def run_chair(
    *, run_id: str, case_id: str, arguments: Sequence[Argument], scores: Sequence[Score],
    red_team: RedTeamReport, privacy_summary: PrivacySummary, judge_summary: JudgeSummary,
    gateway: LLMGateway, incomplete_reasons: Sequence[str] = (),
    failed_turns: Sequence[str] = (), prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
) -> Report:
    """Call the chair when synthesis is possible; otherwise return a bare report."""
    final = final_arguments(arguments)
    if not final:
        return bare_report(
            run_id=run_id, case_id=case_id, arguments=arguments, red_team=red_team,
            privacy_summary=privacy_summary, judge_summary=judge_summary,
            incomplete_reasons=[*incomplete_reasons, "all specialists failed"],
            failed_turns=failed_turns,
        )

    final_ids = {argument.argument_id for argument in final}
    final_scores = [score for score in scores if score.argument_id in final_ids]
    data_blocks = [
        ("Final specialist arguments", render_json(final)),
        ("Final-round judge scores", render_json(final_scores)),
        ("Red-team report", json.dumps(red_team.model_dump(mode="json"), indent=2)),
    ]
    body = prompting.chair_body(data_blocks, prompts_dir)
    draft, _repair_used, failure_reason, _model = call_and_parse_with_repair(
        gateway, role=Role.CHAIR, step=Step.CHAIR, round_number=None, body=body,
        schema_model=ReportDraft, prompts_dir=prompts_dir, retrieved_ids=[],
        find_issues=lambda report: chair_issues(report, final, red_team),
    )
    if draft is None or chair_issues(draft, final, red_team):
        reason = failure_reason or "chair response still failed validation after repair"
        return bare_report(
            run_id=run_id, case_id=case_id, arguments=arguments, red_team=red_team,
            privacy_summary=privacy_summary, judge_summary=judge_summary,
            incomplete_reasons=[*incomplete_reasons, f"chair failed: {reason}"],
            failed_turns=[*failed_turns, Role.CHAIR.value],
        )
    return full_report(
        run_id=run_id, case_id=case_id, draft=draft, arguments=arguments, scores=scores,
        red_team=red_team, privacy_summary=privacy_summary, judge_summary=judge_summary,
        incomplete_reasons=incomplete_reasons, failed_turns=failed_turns,
    )
