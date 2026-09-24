"""Fixed two-round council orchestration with code-enforced short circuits."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from threading import Lock

from council.agents import prompting
from council.agents.chair import run_chair
from council.agents.judge import run_judge
from council.agents.red_team import run_red_team
from council.agents.specialist import run_round1, run_round2
from council.gateway import LLMGateway
from council.kb import KnowledgeBase
from council.models import (
    Argument, ArgumentScoreSummary, CaseContext, Claim, Config, Criterion, CriterionGaps,
    CriterionMeans, FailedJudgeCall, JudgeParticipation, JudgeSummary, RedTeamReport,
    Report, RetrievalResult, RevisionCounts, Role, RoundComparison, RoundMeans, Round2Status, Score, Scorecard,
    SharedScore, UngroundedCounts,
)
from council.scoring import SPECIALIST_ROLES, disagreement_count, final_arguments

JUDGES = (Role.JUDGE_A, Role.JUDGE_B)


@dataclass(frozen=True)
class CouncilRun:
    retrievals: list[RetrievalResult]
    arguments: list[Argument]
    scorecard: Scorecard
    red_team: RedTeamReport | None
    report: Report


def parallel_map(roles: Sequence[Role], call: Callable[[Role], Argument | None]) -> list[Argument]:
    """Run specialist turns concurrently and return deterministic role order."""
    with ThreadPoolExecutor(max_workers=len(SPECIALIST_ROLES)) as pool:
        futures = {role: pool.submit(call, role) for role in roles}
        return [result for role in roles if (result := futures[role].result()) is not None]


def criterion_values(score: Score) -> list[int]:
    return [value for criterion in Criterion if (value := getattr(score, criterion.value)) is not None]


def score_summary(argument: Argument, scores: Sequence[Score], gap: int) -> ArgumentScoreSummary | None:
    rows = [score for score in scores if score.argument_id == argument.argument_id]
    if not rows:
        return None
    means: dict[str, float | None] = {}
    gaps: dict[str, int | None] = {}
    disagreements = 0
    for criterion in Criterion:
        values = [getattr(row, criterion.value) for row in rows
                  if getattr(row, criterion.value) is not None]
        means[criterion.value] = mean(values) if values else None
        if len(rows) == 2 and len(values) == 2:
            difference = abs(values[0] - values[1])
            gaps[criterion.value] = difference
            disagreements += difference >= gap
        else:
            gaps[criterion.value] = None
    return ArgumentScoreSummary(
        argument_id=argument.argument_id, role=argument.role, round=argument.round,
        judges_scored=[row.judge for row in rows], mean=CriterionMeans(**means),
        gap=CriterionGaps(**gaps), disagreement_count=disagreements,
    )


def shared_mean(summary: ArgumentScoreSummary | None) -> float | None:
    if summary is None:
        return None
    values = [summary.mean.groundedness, summary.mean.logic, summary.mean.uncertainty]
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def claims_for(argument: Argument) -> list[Claim]:
    claims = list(argument.claims)
    if argument.rebuttal is not None:
        claims.extend(argument.rebuttal.response_claims)
    return claims


def round_comparison(role: Role, arguments: Sequence[Argument],
                     summaries: Sequence[ArgumentScoreSummary]) -> RoundComparison:
    by_turn = {(argument.role, argument.round): argument for argument in arguments}
    by_id = {summary.argument_id: summary for summary in summaries}
    first = by_turn.get((role, 1))
    second = by_turn.get((role, 2))
    first_score = shared_mean(by_id.get(first.argument_id)) if first is not None else None
    second_score = shared_mean(by_id.get(second.argument_id)) if second is not None else None
    revisions = second.revisions if second is not None and second.revisions is not None else []
    if first is None or first.status == "failed":
        round2_status = Round2Status.SKIPPED
    elif second is not None and second.status == "ok":
        round2_status = Round2Status.OK
    else:
        round2_status = Round2Status.FAILED
    return RoundComparison(
        role=role,
        shared_score=SharedScore(
            round1=first_score, round2=second_score,
            change=(second_score - first_score) if first_score is not None and second_score is not None else None,
        ),
        ungrounded_claims=UngroundedCounts(
            round1=(sum(claim.grounding_status == "ungrounded" for claim in claims_for(first))
                    if first is not None else None),
            round2=(sum(claim.grounding_status == "ungrounded" for claim in claims_for(second))
                    if second is not None else None),
        ),
        revisions=RevisionCounts(
            kept=sum(revision.action == "kept" for revision in revisions),
            revised=sum(revision.action == "revised" for revision in revisions),
            dropped=sum(revision.action == "dropped" for revision in revisions),
        ),
        round2_status=round2_status,
    )


def build_scorecard(
    run_id: str, arguments: Sequence[Argument], scores: Sequence[Score],
    failed_judges: Sequence[FailedJudgeCall], config: Config,
) -> Scorecard:
    summaries = [summary for argument in arguments
                 if (summary := score_summary(argument, scores, config.judging.disagreement_gap)) is not None]
    ungrounded = [claim.claim_id for argument in arguments for claim in claims_for(argument)
                  if claim.grounding_status == "ungrounded"]
    return Scorecard(
        run_id=run_id, scores=list(scores),
        skipped_arguments=[argument.argument_id for argument in arguments if argument.status == "failed"],
        failed_judge_calls=list(failed_judges), per_argument=summaries,
        code_ungrounded_claims=list(dict.fromkeys(ungrounded)),
        round_comparison=[round_comparison(role, arguments, summaries) for role in SPECIALIST_ROLES],
    )


def build_judge_summary(scorecard: Scorecard, arguments: Sequence[Argument]) -> JudgeSummary:
    round_means: dict[int, float | None] = {}
    for round_number in (1, 2):
        values = [value for score in scorecard.scores if score.round == round_number
                  for value in criterion_values(score)]
        round_means[round_number] = mean(values) if values else None
    participation = []
    for judge in JUDGES:
        rows = [score for score in scorecard.scores if score.judge == judge]
        if rows:
            participation.append(JudgeParticipation(
                judge=judge, model=rows[0].model, rounds_scored=sorted({score.round for score in rows}),
            ))
    return JudgeSummary(
        mean_score=RoundMeans(round1=round_means[1], round2=round_means[2]),
        disagreement_count=disagreement_count(scorecard.scores, final_arguments(arguments)),
        judges=participation, failed_judge_calls=scorecard.failed_judge_calls,
        round_comparison=scorecard.round_comparison,
        code_ungrounded_claims=scorecard.code_ungrounded_claims,
    )


def run_council(
    *, run_id: str, case: CaseContext, kb: KnowledgeBase, config: Config, gateway: LLMGateway,
    prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
) -> CouncilRun:
    """Run exactly two specialist rounds, or short-circuit to the reserved chair."""
    retrievals: list[RetrievalResult] = []
    retrieval_lock = Lock()
    arguments: list[Argument] = []
    scores: list[Score] = []
    failed_judges: list[FailedJudgeCall] = []
    incomplete_reasons: list[str] = []

    def collect_retrieval(retrieval: RetrievalResult) -> None:
        with retrieval_lock:
            retrievals.append(retrieval)

    round1 = parallel_map(SPECIALIST_ROLES, lambda role: run_round1(
        role, case, kb, config, gateway, prompts_dir, collect_retrieval))
    arguments.extend(round1)

    def budget_reason() -> str | None:
        state = gateway.budget_state()
        return state.reason if state.exhausted else None

    def judge_round(round_number: int) -> None:
        eligible = [argument for argument in arguments
                    if argument.round == round_number and argument.status != "failed"]
        passage_sources = {
            passage.id: passage.text for passages in kb.passages.values() for passage in passages
        }
        for judge in JUDGES:
            for argument in eligible:
                if budget_reason() is not None:
                    return
                score, failed = run_judge(
                    judge, argument, case, passage_sources, config, gateway, prompts_dir,
                )
                if score is not None:
                    scores.append(score)
                if failed:
                    failed_judges.append(FailedJudgeCall(judge=judge, round=round_number))

    if final_arguments(arguments):
        judge_round(1)

    if budget_reason() is None and final_arguments(arguments):
        round2 = parallel_map(SPECIALIST_ROLES, lambda role: run_round2(
            role, case, kb, config, gateway,
            next(argument for argument in round1 if argument.role == role), round1, scores, prompts_dir,
            collect_retrieval))
        arguments.extend(round2)
        if budget_reason() is None:
            judge_round(2)

    reason = budget_reason()
    if reason is not None:
        incomplete_reasons.append(reason)

    red_team: RedTeamReport | None = None
    if reason is None and final_arguments(arguments):
        red_team = run_red_team(case, arguments, scores, kb.passages.get(Role.RED, ()), gateway, prompts_dir)
        if red_team is None:
            incomplete_reasons.append("red team failed")

    scorecard = build_scorecard(run_id, arguments, scores, failed_judges, config)
    judge_summary = build_judge_summary(scorecard, arguments)
    skip_reason = reason or ("all specialists failed" if not final_arguments(arguments) else "red team failed")
    report = run_chair(
        run_id=run_id, case_id=case.case_id, case=case, arguments=arguments, scores=scores,
        red_team=red_team, privacy_summary=None, judge_summary=judge_summary,
        gateway=gateway, incomplete_reasons=incomplete_reasons, prompts_dir=prompts_dir,
        red_team_skip_reason=skip_reason,
    )
    retrievals.sort(key=lambda item: (item.round, item.role))
    return CouncilRun(retrievals=retrievals, arguments=arguments, scorecard=scorecard,
                      red_team=red_team, report=report)
