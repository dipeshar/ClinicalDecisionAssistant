"""Code-owned dissent and confidence for decision support requiring clinical sign-off."""

from collections.abc import Mapping, Sequence
from statistics import mean

from council.models import (
    Argument, Confidence, ConfidenceInputs, Criterion, Dissent, GroundingStatus,
    Level, Penalty, Recommendation, RedTeamFinding, Role, Round, Score, Stance,
    TurnStatus,
)


SPECIALIST_ROLES = (Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN)
ACCEPTED_STANCES = {
    Recommendation.PROCEED: frozenset({Stance.FOR}),
    Recommendation.PROCEED_WITH_MODIFICATIONS: frozenset({Stance.FOR, Stance.CONDITIONAL}),
    Recommendation.DELAY_PENDING_INVESTIGATION: frozenset({Stance.CONDITIONAL, Stance.AGAINST}),
    Recommendation.DECLINE: frozenset({Stance.AGAINST}),
}


def final_arguments(arguments: Sequence[Argument]) -> list[Argument]:
    """Select R2, falling back to R1 when R2 failed or did not run.

    Callers supply validated turn records, at most one per specialist/round.
    An empty result tells the future orchestrator to skip the chair and write
    a bare report with reason 'all specialists failed' (contract section 8).
    """
    turns = {(argument.role, argument.round): argument for argument in arguments}
    final: list[Argument] = []
    for role in SPECIALIST_ROLES:
        first = turns.get((role, 1))
        if first is None or first.status == TurnStatus.FAILED:
            continue
        second = turns.get((role, 2))
        final.append(second if second is not None and second.status == TurnStatus.OK else first)
    return final


def compute_dissent(
    recommendation: Recommendation,
    arguments: Sequence[Argument],
    role_notes: Mapping[Role, str],
) -> list[Dissent]:
    """Copy dissenters' final positions and chair notes, without rewriting them."""
    return [
        Dissent(role=argument.role, stance=argument.stance,
                argument_id=argument.argument_id, note=role_notes[argument.role])
        for argument in final_arguments(arguments)
        if argument.stance not in ACCEPTED_STANCES[recommendation]
    ]


def council_warning(recommendation: Recommendation, arguments: Sequence[Argument]) -> str | None:
    final = final_arguments(arguments)
    dissenters = sum(argument.stance not in ACCEPTED_STANCES[recommendation] for argument in final)
    if dissenters > len(final) / 2:
        return "More than half of the non-failed specialists dissent. Human clinical sign-off required."
    return None


def judge_component(scores: Sequence[Score]) -> tuple[float, Round | None]:
    """Average individual criterion scores in the latest judged round."""
    for round_number in (2, 1):
        values = [
            value for score in scores if score.round == round_number
            for criterion in Criterion
            if (value := getattr(score, criterion.value)) is not None
        ]
        if values:
            return (mean(values) - 1) / 4 * 100, round_number
    return 0.0, None


def disagreement_count(scores: Sequence[Score], final: Sequence[Argument]) -> int:
    """Count argument/criterion pairs with an absolute two-judge gap >= 2."""
    count = 0
    for argument in final:
        judges = {score.judge: score for score in scores if score.argument_id == argument.argument_id}
        if len(judges) != 2:
            continue
        first, second = judges["JUDGE_A"], judges["JUDGE_B"]
        for criterion in Criterion:
            left, right = getattr(first, criterion.value), getattr(second, criterion.value)
            if left is not None and right is not None and abs(left - right) >= 2:
                count += 1
    return count


def ungrounded_count(final: Sequence[Argument]) -> int:
    """Include rebuttal response claims; count an ID only once if also in claims."""
    claims = {claim.claim_id: claim for argument in final for claim in argument.claims}
    for argument in final:
        if argument.rebuttal is not None:
            claims.update((claim.claim_id, claim) for claim in argument.rebuttal.response_claims)
    return sum(claim.grounding_status == GroundingStatus.UNGROUNDED for claim in claims.values())


def confidence_level(score: float) -> Level:
    if score >= 70:
        return Level.HIGH
    if score >= 40:
        return Level.MEDIUM
    return Level.LOW


def clamp_score(score: float) -> float:
    return min(100.0, max(0.0, score))


def compute_confidence(
    recommendation: Recommendation,
    arguments: Sequence[Argument],
    scores: Sequence[Score],
    findings: Sequence[RedTeamFinding],
) -> Confidence | None:
    """Apply section 12 to validated arguments, raw judge scores and findings.

    No working final argument means a bare report, not a numeric confidence.
    Judge scores must already refer to real, successful turns (section 6).
    Judge averaging selects one round globally; penalties select it per role.
    """
    final = final_arguments(arguments)
    if not final:
        return None
    judge_part, judge_round_used = judge_component(scores)
    accepting = sum(argument.stance in ACCEPTED_STANCES[recommendation] for argument in final)
    agreement_part = accepting / len(final) * 100
    base = 0.5 * judge_part + 0.5 * agreement_part
    ungrounded = ungrounded_count(final)
    high = sum(finding.severity == Level.HIGH for finding in findings)
    disagreements = disagreement_count(scores, final)
    ungrounded_penalty = Penalty(count=ungrounded, penalty=min(20, 5 * ungrounded))
    high_penalty = Penalty(count=high, penalty=min(20, 10 * high))
    disagreement_penalty = Penalty(count=disagreements, penalty=min(10, 5 * disagreements))
    total = ungrounded_penalty.penalty + high_penalty.penalty + disagreement_penalty.penalty
    score = clamp_score(base - total)
    return Confidence(
        score=score, level=confidence_level(score),
        inputs=ConfidenceInputs(
            judge_part=judge_part, judge_round_used=judge_round_used,
            agreement_part=agreement_part, specialists_counted=len(final),
            specialists_accepting=accepting, base=base,
            ungrounded_claims=ungrounded_penalty, high_severity_findings=high_penalty,
            judge_disagreements=disagreement_penalty, total_penalty=total,
        ),
    )
