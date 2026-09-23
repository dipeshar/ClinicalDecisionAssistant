"""Build checked full and bare reports from collected council data."""

from collections.abc import Iterable, Sequence

from council.models import (
    Argument, Citation, DISCLAIMER, InjectionCheck, JudgeSummary, PrivacySummary,
    RedTeamReport, Report, ReportDraft, ReportStatus, Score,
)
from council.scoring import compute_confidence, compute_dissent, council_warning, final_arguments


def collected_citations(arguments: Sequence[Argument]) -> list[Citation]:
    """All citations collected so far, in argument/claim order without duplicates."""
    citations: list[Citation] = []
    seen: set[tuple[str, str, bool, str]] = set()
    for argument in arguments:
        claims = list(argument.claims)
        if argument.rebuttal is not None:
            claims.extend(argument.rebuttal.response_claims)
        for claim in claims:
            for citation in claim.citations:
                key = (citation.passage_id, citation.quote, citation.verified, citation.verify_note)
                if key not in seen:
                    seen.add(key)
                    citations.append(citation)
    return citations


def failed_turn_ids(arguments: Sequence[Argument], judge_summary: JudgeSummary) -> list[str]:
    ids = [argument.argument_id for argument in arguments if argument.status == "failed"]
    ids.extend(call.judge for call in judge_summary.failed_judge_calls if call.judge not in ids)
    return ids


def derived_incomplete_reasons(arguments: Sequence[Argument], judge_summary: JudgeSummary) -> list[str]:
    reasons = [f"{argument.argument_id} failed: {argument.failure_reason}"
               for argument in arguments if argument.status == "failed"]
    reasons.extend(f"{call.judge} failed in Round {call.round}" for call in judge_summary.failed_judge_calls)
    return reasons


def merge_reasons(derived: Iterable[str], supplied: Iterable[str]) -> list[str]:
    return list(dict.fromkeys([*derived, *supplied]))


def bare_report(
    *, run_id: str, case_id: str, arguments: Sequence[Argument], red_team: RedTeamReport,
    privacy_summary: PrivacySummary, judge_summary: JudgeSummary,
    incomplete_reasons: Sequence[str], failed_turns: Sequence[str] = (),
) -> Report:
    reasons = merge_reasons(derived_incomplete_reasons(arguments, judge_summary), incomplete_reasons)
    turns = list(dict.fromkeys([*failed_turn_ids(arguments, judge_summary), *failed_turns]))
    return Report(
        run_id=run_id, case_id=case_id, status=ReportStatus.INCOMPLETE,
        incomplete_reasons=reasons, failed_turns=turns, recommendation=None,
        recommendation_basis=[], confidence=None, council_warning=None,
        strongest_for=[], strongest_against=[], required_actions=[], role_notes={}, dissent=[],
        red_team_findings=red_team.findings, injection_check=red_team.injection_check,
        privacy_summary=privacy_summary, judge_summary=judge_summary, narrative="",
        citations_index=collected_citations(arguments), disclaimer=DISCLAIMER, human_decision=None,
    )


def full_report(
    *, run_id: str, case_id: str, draft: ReportDraft, arguments: Sequence[Argument],
    scores: Sequence[Score], red_team: RedTeamReport, privacy_summary: PrivacySummary,
    judge_summary: JudgeSummary, incomplete_reasons: Sequence[str] = (),
    failed_turns: Sequence[str] = (),
) -> Report:
    reasons = merge_reasons(derived_incomplete_reasons(arguments, judge_summary), incomplete_reasons)
    turns = list(dict.fromkeys([*failed_turn_ids(arguments, judge_summary), *failed_turns]))
    findings = red_team.findings
    confidence = compute_confidence(draft.recommendation, arguments, scores, findings)
    if confidence is None:
        raise ValueError("a full report needs a non-failed final argument")
    dissent = compute_dissent(draft.recommendation, arguments, draft.role_notes)
    return Report(
        run_id=run_id, case_id=case_id,
        status=ReportStatus.INCOMPLETE if reasons else ReportStatus.COMPLETE,
        incomplete_reasons=reasons, failed_turns=turns,
        recommendation=draft.recommendation, recommendation_basis=draft.recommendation_basis,
        confidence=confidence, council_warning=council_warning(draft.recommendation, arguments),
        strongest_for=draft.strongest_for, strongest_against=draft.strongest_against,
        required_actions=draft.required_actions, role_notes=draft.role_notes, dissent=dissent,
        red_team_findings=findings, injection_check=red_team.injection_check,
        privacy_summary=privacy_summary, judge_summary=judge_summary, narrative=draft.narrative,
        citations_index=collected_citations(final_arguments(arguments)), disclaimer=DISCLAIMER,
        human_decision=None,
    )
