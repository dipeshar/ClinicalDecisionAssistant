"""Synthetic arithmetic examples; no provider or model calls."""

import pytest

from council.models import Argument, Claim, Rebuttal, Recommendation, RedTeamFinding, Role, Score
from council.scoring import (
    clamp_score, compute_confidence, compute_dissent, confidence_level,
    council_warning, disagreement_count, final_arguments, judge_component,
)


def argument(role: str = "SURG", round: int = 1, stance: str | None = "for",
             ungrounded: int = 0) -> Argument:
    argument_id = f"R{round}-{role}"
    return Argument(
        argument_id=argument_id, role=role, round=round, stance=stance,
        summary="Synthetic position", claims=[
            Claim(claim_id=f"{argument_id}-C{i}", text="Synthetic claim", citations=[],
                  grounding_status="ungrounded") for i in range(1, ungrounded + 1)
        ], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
        stance_changed=False, retrieved_passage_ids=[], repair_used=False,
        status="failed" if stance is None else "ok",
        failure_reason="Synthetic failure" if stance is None else None,
    )


def score(arg: Argument, ratings: tuple[int, ...] = (5, 5, 5), judge: str = "JUDGE_A") -> Score:
    return Score(judge=judge, argument_id=arg.argument_id, model="fake/judge", round=arg.round,
                 groundedness=ratings[0], logic=ratings[1], uncertainty=ratings[2],
                 counterarguments=ratings[3] if arg.round == 2 else None,
                 justification={}, untraceable_claims=[], feedback=[])


def finding(number: int, severity: str = "high") -> RedTeamFinding:
    return RedTeamFinding(finding_id=f"RT-{number}", category="missing_info", severity=severity,
                          description="Synthetic missing information", evidence_ids=["CASE-tests"],
                          affected_roles=[Role.SURG], suggested_action="Human review")


@pytest.mark.parametrize("recommendation,accepted", [
    ("proceed", {"for"}), ("proceed_with_modifications", {"for", "conditional"}),
    ("delay_pending_investigation", {"conditional", "against"}), ("decline", {"against"}),
])
@pytest.mark.parametrize("stance", ["for", "against", "conditional"])
def test_stance_table(recommendation: str, accepted: set[str], stance: str) -> None:
    arg = argument(stance=stance)
    rec = Recommendation(recommendation)
    dissent = compute_dissent(rec, [arg], {Role.SURG: "Exact chair note"})
    expected = [] if stance in accepted else [dict(role="SURG", stance=stance,
                                                 argument_id="R1-SURG", note="Exact chair note")]
    assert [row.model_dump(mode="json") for row in dissent] == expected
    confidence = compute_confidence(rec, [arg], [], [])
    assert confidence.inputs.agreement_part == (100 if stance in accepted else 0)
    assert confidence.inputs.specialists_accepting == (1 if stance in accepted else 0)


def test_final_round_selection_and_failed_specialists() -> None:
    first = argument(stance="against")
    second = argument(round=2)
    failed_first = argument("PHYS", stance=None)
    # Even inconsistent input cannot revive a failed Round 1 specialist.
    invalid_second = argument("PHYS", round=2)
    structural = argument("CHAIR")
    assert final_arguments([second, failed_first, structural, first, invalid_second]) == [second]
    assert compute_dissent(Recommendation.PROCEED, [first, second], {}) == []


@pytest.mark.parametrize("failed_second", [False, True])
def test_round2_failed_or_skipped_falls_back(failed_second: bool) -> None:
    first = argument(stance="against", ungrounded=1)
    args = [first, argument("PHYS", stance=None)]
    if failed_second:
        args.append(argument(round=2, stance=None))
    assert final_arguments(args) == [first]
    dissent = compute_dissent(Recommendation.PROCEED, args, {Role.SURG: "Keep this note"})
    assert dissent[0].argument_id == "R1-SURG" and dissent[0].note == "Keep this note"
    result = compute_confidence(Recommendation.PROCEED, args, [score(first)], [])
    assert result.inputs.specialists_counted == 1
    assert result.inputs.specialists_accepting == 0
    assert result.inputs.judge_round_used == 1
    assert result.inputs.ungrounded_claims.model_dump() == {"count": 1, "penalty": 5}


@pytest.mark.parametrize("args", [[], [argument(role, stance=None) for role in ("SURG", "PHYS", "ANAES", "ADMIN")]])
def test_no_working_final_argument_has_no_confidence(args: list[Argument]) -> None:
    assert final_arguments(args) == []
    assert compute_confidence(Recommendation.PROCEED, args, [], []) is None
    assert compute_dissent(Recommendation.PROCEED, args, {}) == []
    assert council_warning(Recommendation.PROCEED, args) is None


@pytest.mark.parametrize("stances,warning", [
    (["for", "against"], False), (["for", "against", "against"], True),
    (["for", "for", "against", "against"], False), (["against", None, None, None], True),
])
def test_warning_requires_strict_majority(stances: list[str | None], warning: bool) -> None:
    args = [argument(role, stance=stance) for role, stance in zip(("SURG", "PHYS", "ANAES", "ADMIN"), stances)]
    assert (council_warning(Recommendation.PROCEED, args) is not None) == warning


def test_judge_round2_preferred_and_all_values_weighted_equally() -> None:
    first, second, other = argument(), argument(round=2), argument("PHYS", round=2)
    scores = [score(first, (1, 1, 1)), score(second, (1, 2, 3, 4)),
              score(second, (5, 4, 3, 2), "JUDGE_B"), score(other, (5, 5, 5, 5))]
    part, round_used = judge_component(scores)
    assert round_used == 2
    assert part == pytest.approx(((44 / 12) - 1) / 4 * 100)


def test_judge_round1_fallback_even_when_round2_arguments_exist() -> None:
    first, second = argument(), argument(round=2)
    result = compute_confidence(Recommendation.PROCEED, [first, second], [score(first, (1, 3, 5))], [])
    assert result.inputs.judge_round_used == 1
    assert result.inputs.judge_part == 50
    assert result.inputs.base == 75
    assert result.score == 75


def test_no_judges_and_failed_turns_lower_confidence() -> None:
    args = [argument(), argument("PHYS", stance="against"), argument("ADMIN", stance=None)]
    result = compute_confidence(Recommendation.PROCEED, args, [], [])
    assert result.inputs.model_dump() == dict(
        judge_part=0, judge_round_used=None, agreement_part=50, specialists_counted=2,
        specialists_accepting=1, base=25, ungrounded_claims=dict(count=0, penalty=0),
        high_severity_findings=dict(count=0, penalty=0), judge_disagreements=dict(count=0, penalty=0),
        total_penalty=0,
    )
    assert result.score == 25 and result.level == "low"


@pytest.mark.parametrize("count,penalty", [(0, 0), (1, 5), (4, 20), (5, 20)])
def test_ungrounded_penalty_rate_and_cap(count: int, penalty: int) -> None:
    arg = argument(ungrounded=count)
    result = compute_confidence(Recommendation.PROCEED, [arg], [score(arg)], [])
    assert result.inputs.ungrounded_claims.model_dump() == dict(count=count, penalty=penalty)
    assert result.score == 100 - penalty


@pytest.mark.parametrize("count,penalty", [(0, 0), (1, 10), (2, 20), (3, 20)])
def test_high_findings_penalty_rate_and_cap(count: int, penalty: int) -> None:
    arg = argument()
    findings = [finding(i) for i in range(count)] + [finding(8, "low"), finding(9, "medium")]
    result = compute_confidence(Recommendation.PROCEED, [arg], [score(arg)], findings)
    assert result.inputs.high_severity_findings.model_dump() == dict(count=count, penalty=penalty)
    assert result.score == 100 - penalty


@pytest.mark.parametrize("ratings,expected", [((4, 4, 4), 0), ((3, 5, 5), 1), ((3, 3, 5), 2), ((3, 3, 3), 3)])
def test_disagreement_penalty_rate_and_cap(ratings: tuple[int, ...], expected: int) -> None:
    arg = argument()
    scores = [score(arg), score(arg, ratings, "JUDGE_B")]
    result = compute_confidence(Recommendation.PROCEED, [arg], scores, [])
    assert result.inputs.judge_disagreements.model_dump() == dict(count=expected, penalty=min(10, expected * 5))


def test_disagreements_absolute_per_criterion_and_one_judge_zero() -> None:
    arg = argument(round=2)
    first, second = score(arg, (1, 5, 3, 1)), score(arg, (3, 3, 4, 5), "JUDGE_B")
    assert disagreement_count([first, second], [arg]) == 3
    assert disagreement_count([second, first], [arg]) == 3
    assert disagreement_count([first], [arg]) == 0
    assert disagreement_count([], [arg]) == 0


def test_final_penalties_ignore_fixed_and_dropped_round1_claims() -> None:
    first, second = argument(ungrounded=5), argument(round=2)
    second.claims = [Claim(claim_id="R2-SURG-C1", text="Fixed synthetic claim", citations=[], grounding_status="grounded")]
    scores = [score(first), score(first, (1, 1, 1), "JUDGE_B"), score(second, (5, 5, 5, 5))]
    result = compute_confidence(Recommendation.PROCEED, [first, second], scores, [])
    assert result.score == 100
    assert result.inputs.ungrounded_claims.count == 0
    assert result.inputs.judge_disagreements.count == 0


def test_penalties_fall_back_per_role_not_per_judged_round() -> None:
    surg1, surg2 = argument(ungrounded=3), argument(round=2)
    phys1, phys2 = argument("PHYS", ungrounded=2), argument("PHYS", round=2, stance=None)
    scores = [score(phys1), score(phys1, (3, 5, 5), "JUDGE_B"), score(surg2, (5, 5, 5, 5))]
    result = compute_confidence(Recommendation.PROCEED, [surg1, surg2, phys1, phys2], scores, [])
    assert result.inputs.judge_part == 100 and result.inputs.judge_round_used == 2
    assert result.inputs.ungrounded_claims.model_dump() == dict(count=2, penalty=10)
    assert result.inputs.judge_disagreements.model_dump() == dict(count=1, penalty=5)
    assert result.score == 85


def test_rebuttal_claims_count_once_by_id() -> None:
    first, second = argument(), argument(round=2, ungrounded=1)
    second.rebuttal = Rebuttal(target_argument_id="R1-PHYS", target_claim_id="R1-PHYS-C1",
                              why_strongest="Synthetic opposition", response_claims=[second.claims[0],
                                  Claim(claim_id="R2-SURG-C2", text="Synthetic response", citations=[], grounding_status="ungrounded")])
    result = compute_confidence(Recommendation.PROCEED, [first, second], [], [])
    assert result.inputs.ungrounded_claims.model_dump() == dict(count=2, penalty=10)


def test_combined_penalties_and_lower_clamping() -> None:
    arg = argument(stance="against", ungrounded=5)
    scores = [score(arg, (1, 1, 1)), score(arg, (3, 3, 3), "JUDGE_B")]
    result = compute_confidence(Recommendation.PROCEED, [arg], scores, [finding(i) for i in range(3)])
    assert result.inputs.base == 12.5
    assert result.inputs.total_penalty == 50
    assert result.score == 0 and result.level == "low"


@pytest.mark.parametrize("value,expected", [(-10, 0), (0, 0), (40.5, 40.5), (100, 100), (110, 100)])
def test_clamping(value: float, expected: float) -> None:
    assert clamp_score(value) == expected


@pytest.mark.parametrize("value,level", [(0, "low"), (39.99, "low"), (40, "medium"), (69.99, "medium"), (70, "high"), (100, "high")])
def test_level_boundaries(value: float, level: str) -> None:
    assert confidence_level(value) == level


@pytest.mark.parametrize("ratings,findings,expected,level", [
    ((1, 1, 1, 1), 1, 40, "medium"),
])
def test_level_boundaries_through_formula(ratings: tuple[int, ...], findings: int, expected: float, level: str) -> None:
    first, second = argument(), argument(round=2)
    result = compute_confidence(Recommendation.PROCEED, [first, second], [score(second, ratings)],
                                [finding(i) for i in range(findings)])
    assert result.score == expected and result.level == level


def test_high_boundary_through_formula() -> None:
    args = [argument(role) for role in ("SURG", "PHYS", "ANAES")]
    scores = [score(arg, (4, 4, 4), judge) for arg in args[:2] for judge in ("JUDGE_A", "JUDGE_B")]
    scores.append(score(args[2], (5, 5, 5)))
    result = compute_confidence(Recommendation.PROCEED, args, scores, [finding(1), finding(2)])
    assert result.score == 70 and result.level == "high"
