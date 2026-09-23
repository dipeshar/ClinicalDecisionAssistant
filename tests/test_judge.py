"""Judges: one call per round, shuffled order, skipped failed arguments, feedback limits,
argument_id-based score matching. FakeProvider only; judges call real models starting at T17.
"""

import json
from pathlib import Path

from council.agents import judge as j
from council.budget import Budget
from council.gateway import LLMGateway
from council.models import CaseSection, CaseContext, Citation, Claim, Argument, Config, Role
from council.providers.base import ProviderError
from council.providers.fake import FakeProvider, Scripted
from council.trace import TraceWriter

REAL_PROMPTS = Path("prompts")


def case_context() -> CaseContext:
    sections = [
        CaseSection(id="CASE-tests", heading="Tests and Imaging", text="Creatinine 1.1 mg/dL, eGFR 78.",
                   flagged=False, flag_reasons=[]),
    ]
    return CaseContext(case_id="synthetic01", source_file="cases/synthetic01.md", case_hash="a" * 64,
                       title="Synthetic exercise", sections=sections, missing_sections=[], injection_flags=[])


def argument(role: Role, round_number: int = 1, status: str = "ok", stance: str | None = "for") -> Argument:
    argument_id = f"R{round_number}-{role.value}"
    if status == "failed":
        return Argument(argument_id=argument_id, role=role, round=round_number, stance=None, summary="",
                        claims=[], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
                        stance_changed=False, retrieved_passage_ids=[], repair_used=False,
                        status="failed", failure_reason="Synthetic failure")
    claim = Claim(claim_id=f"{argument_id}-C1", text="Renal function is normal.",
                 citations=[Citation(passage_id="SURG-KB-01", quote="Operative risk is low when renal function is normal",
                                    source_type="kb", verified=True, verify_note="")],
                 grounding_status="grounded")
    return Argument(argument_id=argument_id, role=role, round=round_number, stance=stance,
                    summary="Synthetic summary.", claims=[claim], conditions=[], uncertainties=[],
                    rebuttal=None, revisions=None, stance_changed=False, retrieved_passage_ids=["SURG-KB-01"],
                    repair_used=False, status="ok", failure_reason=None)


PASSAGE_SOURCES = {"SURG-KB-01": "Operative risk is low when renal function is normal and no "
                                "major comorbidities are present in this synthetic patient population."}


def score_json(argument_ids: list[str], *, counterarguments: bool = False, feedback: list | None = None) -> str:
    entries = []
    for argument_id in argument_ids:
        entry = {
            "argument_id": argument_id,
            "groundedness": 5, "logic": 5, "uncertainty": 5,
            "counterarguments": 4 if counterarguments else None,
            "justification": {"groundedness": "Well cited.", "logic": "Coherent.", "uncertainty": "Clear."},
            "untraceable_claims": [],
            "feedback": feedback if feedback is not None else [],
        }
        if counterarguments:
            entry["justification"]["counterarguments"] = "Engages the opposing claim."
        entries.append(entry)
    return json.dumps(entries)


def make_gateway(config: Config, tmp_path: Path, script: list) -> tuple[LLMGateway, Path]:
    provider = FakeProvider("fake", script)
    budget = Budget(config.budget)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, "run-judge-synthetic")
    return LLMGateway(config, budget, trace, {"fake": provider}, sleep_fn=lambda seconds: None), trace_path


def trace_events(trace_path: Path) -> list[dict]:
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]


def reverse_shuffle(items: list) -> None:
    items.reverse()


def test_one_call_scores_every_non_failed_argument_of_the_round(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R1-SURG", "R1-PHYS"]), tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert len(scores) == 2
    assert order == ["R1-SURG", "R1-PHYS"]
    assert {score.argument_id for score in scores} == {"R1-SURG", "R1-PHYS"}
    assert all(score.judge == "JUDGE_A" and score.round == 1 for score in scores)
    assert all(score.model == "fake/judge" for score in scores)
    assert all(score.groundedness == 5 and score.logic == 5 and score.uncertainty == 5 for score in scores)
    prompt = trace_events(trace_path)[0]["prompt"]
    assert "Creatinine 1.1 mg/dL, eGFR 78." in prompt
    assert "R1-SURG" in prompt and "R1-PHYS" in prompt
    assert PASSAGE_SOURCES["SURG-KB-01"] in prompt


def test_shuffled_order_is_recorded_and_matches_what_was_scored(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS), argument(Role.ANAES)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R1-SURG", "R1-PHYS", "R1-ANAES"]), tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=reverse_shuffle)

    assert failed is False
    assert order == ["R1-ANAES", "R1-PHYS", "R1-SURG"]
    # The response listed scores in the original (unshuffled) order; matching is by
    # argument_id, not position, so the returned scores still follow the shown order.
    assert [score.argument_id for score in scores] == order
    # judge.md itself now mentions "R1-SURG" as an inline example, so search for the
    # argument-block heading specifically, not the bare ID, to avoid that collision.
    prompt = trace_events(trace_path)[0]["prompt"]
    assert prompt.index("### R1-ANAES") < prompt.index("### R1-PHYS") < prompt.index("### R1-SURG")


def test_failed_and_wrong_round_arguments_are_skipped(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS, status="failed"), argument(Role.ANAES, round_number=2)]
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=score_json(["R1-SURG"]), tokens_in=5, tokens_out=5)])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert order == ["R1-SURG"]
    assert [score.argument_id for score in scores] == ["R1-SURG"]


def test_no_eligible_arguments_makes_no_gateway_call(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG, status="failed")]
    provider = FakeProvider("fake", [Scripted()])
    gateway, _ = (LLMGateway(config, Budget(config.budget), TraceWriter(tmp_path / "trace.jsonl", "run-synthetic"),
                             {"fake": provider}, sleep_fn=lambda s: None), None)

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS)

    assert scores == [] and order == [] and failed is False
    assert provider.calls_made == 0


def test_feedback_is_cut_to_the_configured_limits(config: Config, tmp_path: Path) -> None:
    notes = [{"claim_id": None, "note": "word " * 41} for _ in range(7)]
    args = [argument(Role.SURG)]
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R1-SURG"], feedback=notes), tokens_in=5, tokens_out=5),
    ])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert len(scores[0].feedback) == config.judging.feedback_max_notes
    assert all(len(note.note.split()) == config.judging.feedback_max_words for note in scores[0].feedback)


def test_round2_feedback_is_forced_empty(config: Config, tmp_path: Path) -> None:
    notes = [{"claim_id": None, "note": "Should not appear."}]
    args = [argument(Role.SURG, round_number=2)]
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R2-SURG"], counterarguments=True, feedback=notes), tokens_in=5, tokens_out=5),
    ])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 2, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].feedback == []
    assert scores[0].counterarguments == 4


def test_round1_counterarguments_is_forced_null(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG)]
    entry = json.loads(score_json(["R1-SURG"]))
    entry[0]["counterarguments"] = 3  # the model wrongly scores counterarguments in Round 1
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=json.dumps(entry), tokens_in=5, tokens_out=5)])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].counterarguments is None


def test_round2_missing_counterarguments_triggers_repair(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG, round_number=2)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R2-SURG"], counterarguments=False), tokens_in=5, tokens_out=5),
        Scripted(raw_output=score_json(["R2-SURG"], counterarguments=True), tokens_in=5, tokens_out=5),
    ])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 2, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].counterarguments == 4
    events = trace_events(trace_path)
    assert [event["repair"] for event in events] == [False, True]


def test_scores_are_matched_by_argument_id_not_response_order(config: Config, tmp_path: Path) -> None:
    """The model's response can list scores in any order; matching is by argument_id."""
    args = [argument(Role.SURG), argument(Role.PHYS)]
    reordered = json.dumps(list(reversed(json.loads(score_json(["R1-SURG", "R1-PHYS"])))))
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=reordered, tokens_in=5, tokens_out=5)])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert order == ["R1-SURG", "R1-PHYS"]
    assert [score.argument_id for score in scores] == ["R1-SURG", "R1-PHYS"]


def test_duplicate_argument_id_triggers_repair(config: Config, tmp_path: Path) -> None:
    """One argument scored twice, the other not at all: a real judge mistake, not just a count."""
    args = [argument(Role.SURG), argument(Role.PHYS)]
    duplicated = score_json(["R1-SURG", "R1-SURG"])  # same length as expected (2), but wrong
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=duplicated, tokens_in=5, tokens_out=5),
        Scripted(raw_output=score_json(["R1-SURG", "R1-PHYS"]), tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert order == ["R1-SURG", "R1-PHYS"]
    assert {score.argument_id for score in scores} == {"R1-SURG", "R1-PHYS"}
    events = trace_events(trace_path)
    assert [event["repair"] for event in events] == [False, True]
    assert "scored more than once" in events[1]["prompt"] and "R1-SURG" in events[1]["prompt"]


def test_unknown_argument_id_triggers_repair(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(["R1-PHYS"]), tokens_in=5, tokens_out=5),  # PHYS wasn't shown at all
        Scripted(raw_output=score_json(["R1-SURG"]), tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert order == ["R1-SURG"]
    assert [score.argument_id for score in scores] == ["R1-SURG"]
    events = trace_events(trace_path)
    assert "not shown" in events[1]["prompt"] and "R1-PHYS" in events[1]["prompt"]


def test_wrong_argument_ids_still_wrong_after_repair_fails_the_call(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS)]
    duplicated = score_json(["R1-SURG", "R1-SURG"])
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=duplicated, tokens_in=5, tokens_out=5),
        Scripted(raw_output=duplicated, tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is True
    assert scores == [] and order == []


def test_bad_json_twice_fails_the_call(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG)]
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output="not valid json"),
        Scripted(raw_output="still not valid json"),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is True
    assert scores == [] and order == []


def test_gateway_refusal_fails_the_call(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG)]
    gateway, _ = make_gateway(config, tmp_path, [ProviderError])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is True
    assert scores == [] and order == []


def test_render_argument_shows_citation_source_text() -> None:
    text = j.render_argument(argument(Role.SURG), PASSAGE_SOURCES)
    assert "R1-SURG" in text
    assert "cites SURG-KB-01" in text
    assert PASSAGE_SOURCES["SURG-KB-01"] in text
