"""Judges: one call per round, shuffled order, skipped failed arguments, feedback limits.

FakeProvider only; judges call real models starting at T17, not here.
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


def score_json(count: int, *, counterarguments: bool = False, feedback: list | None = None) -> str:
    entry = {
        "groundedness": 5, "logic": 5, "uncertainty": 5,
        "counterarguments": 4 if counterarguments else None,
        "justification": {"groundedness": "Well cited.", "logic": "Coherent.", "uncertainty": "Clear."},
        "untraceable_claims": [],
        "feedback": feedback if feedback is not None else [],
    }
    if counterarguments:
        entry["justification"]["counterarguments"] = "Engages the opposing claim."
    return json.dumps([entry] * count)


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
    gateway, trace_path = make_gateway(config, tmp_path, [Scripted(raw_output=score_json(2), tokens_in=5, tokens_out=5)])

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
    gateway, trace_path = make_gateway(config, tmp_path, [Scripted(raw_output=score_json(3), tokens_in=5, tokens_out=5)])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=reverse_shuffle)

    assert failed is False
    assert order == ["R1-ANAES", "R1-PHYS", "R1-SURG"]
    assert [score.argument_id for score in scores] == order
    prompt = trace_events(trace_path)[0]["prompt"]
    assert prompt.index("R1-ANAES") < prompt.index("R1-PHYS") < prompt.index("R1-SURG")


def test_failed_and_wrong_round_arguments_are_skipped(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS, status="failed"), argument(Role.ANAES, round_number=2)]
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=score_json(1), tokens_in=5, tokens_out=5)])

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
        Scripted(raw_output=score_json(1, feedback=notes), tokens_in=5, tokens_out=5),
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
        Scripted(raw_output=score_json(1, counterarguments=True, feedback=notes), tokens_in=5, tokens_out=5),
    ])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 2, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].feedback == []
    assert scores[0].counterarguments == 4


def test_round1_counterarguments_is_forced_null(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG)]
    raw = score_json(1)
    entry = json.loads(raw)
    entry[0]["counterarguments"] = 3  # the model wrongly scores counterarguments in Round 1
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=json.dumps(entry), tokens_in=5, tokens_out=5)])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].counterarguments is None


def test_round2_missing_counterarguments_triggers_repair(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG, round_number=2)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(1, counterarguments=False), tokens_in=5, tokens_out=5),
        Scripted(raw_output=score_json(1, counterarguments=True), tokens_in=5, tokens_out=5),
    ])

    scores, _order, failed = j.run_judge(Role.JUDGE_A, 2, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                         REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert scores[0].counterarguments == 4
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["repair"] for event in events] == [False, True]


def test_array_length_mismatch_triggers_repair(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG), argument(Role.PHYS)]
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json(1), tokens_in=5, tokens_out=5),  # only one score for two arguments
        Scripted(raw_output=score_json(2), tokens_in=5, tokens_out=5),
    ])

    scores, order, failed = j.run_judge(Role.JUDGE_A, 1, args, case_context(), PASSAGE_SOURCES, config, gateway,
                                        REAL_PROMPTS, shuffle=lambda items: None)

    assert failed is False
    assert len(scores) == 2 and order == ["R1-SURG", "R1-PHYS"]


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
