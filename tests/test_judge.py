"""Judges: one call per non-failed argument, skipped failed arguments, feedback limits,
argument_id-based score matching. FakeProvider only; judges call real models starting at T17.
"""

import json
from pathlib import Path

import pytest

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


def score_json(argument_id: str, *, counterarguments: bool = False, feedback: list | None = None) -> str:
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
    return json.dumps(entry)


def make_gateway(config: Config, tmp_path: Path, script: list) -> tuple[LLMGateway, Path]:
    provider = FakeProvider("fake", script)
    budget = Budget(config.budget)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, "run-judge-synthetic")
    return LLMGateway(config, budget, trace, {"fake": provider}, sleep_fn=lambda seconds: None), trace_path


def trace_events(trace_path: Path) -> list[dict]:
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]


def run_one(config: Config, tmp_path: Path, script: list, *, shown: Argument | None = None):
    gateway, trace_path = make_gateway(config, tmp_path, script)
    score, failed = j.run_judge(
        Role.JUDGE_A, shown or argument(Role.SURG), case_context(), PASSAGE_SOURCES,
        config, gateway, REAL_PROMPTS,
    )
    return score, failed, trace_path


def test_one_call_scores_one_argument_with_single_object_schema(config: Config, tmp_path: Path) -> None:
    score, failed, trace_path = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R1-SURG"), tokens_in=5, tokens_out=5),
    ])

    assert failed is False and score is not None
    assert score.argument_id == "R1-SURG" and score.judge == "JUDGE_A" and score.round == 1
    assert score.model == "fake/judge"
    prompt = trace_events(trace_path)[0]["prompt"]
    assert "### R1-SURG (SURG, round 1)" in prompt
    assert "### R1-PHYS" not in prompt
    schema = json.loads(prompt.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
    assert schema["type"] == "object" and "items" not in schema


def test_failed_argument_is_rejected_before_gateway(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [Scripted()])
    with pytest.raises(ValueError, match="failed argument"):
        j.run_judge(Role.JUDGE_A, argument(Role.SURG, status="failed"), case_context(),
                    PASSAGE_SOURCES, config, gateway, REAL_PROMPTS)


def test_feedback_is_cut_to_the_configured_limits(config: Config, tmp_path: Path) -> None:
    notes = [{"claim_id": None, "note": "word " * 41} for _ in range(7)]
    score, failed, _ = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R1-SURG", feedback=notes), tokens_in=5, tokens_out=5),
    ])
    assert failed is False and score is not None
    assert len(score.feedback) == config.judging.feedback_max_notes
    assert all(len(note.note.split()) == config.judging.feedback_max_words for note in score.feedback)


def test_round2_feedback_is_forced_empty(config: Config, tmp_path: Path) -> None:
    notes = [{"claim_id": None, "note": "Should not appear."}]
    score, failed, _ = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R2-SURG", counterarguments=True, feedback=notes)),
    ], shown=argument(Role.SURG, round_number=2))
    assert failed is False and score is not None
    assert score.feedback == [] and score.counterarguments == 4


def test_round1_counterarguments_is_forced_null(config: Config, tmp_path: Path) -> None:
    entry = json.loads(score_json("R1-SURG"))
    entry["counterarguments"] = 3
    score, failed, _ = run_one(config, tmp_path, [Scripted(raw_output=json.dumps(entry))])
    assert failed is False and score is not None and score.counterarguments is None


def test_round2_missing_counterarguments_triggers_repair(config: Config, tmp_path: Path) -> None:
    score, failed, trace_path = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R2-SURG")),
        Scripted(raw_output=score_json("R2-SURG", counterarguments=True)),
    ], shown=argument(Role.SURG, round_number=2))
    assert failed is False and score is not None and score.counterarguments == 4
    assert [event["repair"] for event in trace_events(trace_path)] == [False, True]


def test_missing_argument_id_triggers_repair(config: Config, tmp_path: Path) -> None:
    missing = json.loads(score_json("R1-SURG"))
    del missing["argument_id"]
    score, failed, trace_path = run_one(config, tmp_path, [
        Scripted(raw_output=json.dumps(missing)), Scripted(raw_output=score_json("R1-SURG")),
    ])
    assert failed is False and score is not None and score.argument_id == "R1-SURG"
    assert [event["repair"] for event in trace_events(trace_path)] == [False, True]


def test_unknown_argument_id_triggers_repair(config: Config, tmp_path: Path) -> None:
    score, failed, trace_path = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R1-PHYS")), Scripted(raw_output=score_json("R1-SURG")),
    ])
    assert failed is False and score is not None and score.argument_id == "R1-SURG"
    events = trace_events(trace_path)
    assert [event["repair"] for event in events] == [False, True]
    assert "must match the one argument shown: R1-SURG" in events[1]["prompt"]


def test_wrong_argument_id_still_wrong_after_repair_fails_only_that_call(config: Config, tmp_path: Path) -> None:
    score, failed, _ = run_one(config, tmp_path, [
        Scripted(raw_output=score_json("R1-PHYS")), Scripted(raw_output=score_json("R1-PHYS")),
    ])
    assert failed is True and score is None


def test_bad_json_twice_fails_the_call(config: Config, tmp_path: Path) -> None:
    score, failed, _ = run_one(config, tmp_path, [
        Scripted(raw_output="not valid json"), Scripted(raw_output="still not valid json"),
    ])
    assert failed is True and score is None


def test_gateway_refusal_fails_the_call(config: Config, tmp_path: Path) -> None:
    score, failed, _ = run_one(config, tmp_path, [ProviderError])
    assert failed is True and score is None


def test_render_argument_shows_citation_id_and_quote_without_source_text() -> None:
    text = j.render_argument(argument(Role.SURG))
    assert "R1-SURG" in text
    assert 'cites SURG-KB-01: "Operative risk is low when renal function is normal"' in text
    assert PASSAGE_SOURCES["SURG-KB-01"] not in text


def test_render_shared_sources_writes_each_cited_source_once() -> None:
    text = j.render_shared_sources([argument(Role.SURG), argument(Role.PHYS)], PASSAGE_SOURCES)
    assert text.count("### SURG-KB-01") == 1
    assert text.count(PASSAGE_SOURCES["SURG-KB-01"]) == 1


def test_cited_case_section_moves_to_shared_sources_without_duplication(config: Config, tmp_path: Path) -> None:
    shown = argument(Role.SURG)
    case_citation = Citation(
        passage_id="CASE-tests", quote="Creatinine 1.1 mg/dL", source_type="case",
        verified=True, verify_note="",
    )
    shown = shown.model_copy(update={
        "claims": [shown.claims[0].model_copy(update={
            "citations": [*shown.claims[0].citations, case_citation],
        })],
    })
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=score_json("R1-SURG"), tokens_in=5, tokens_out=5),
    ])

    score, failed = j.run_judge(
        Role.JUDGE_A, shown, case_context(), PASSAGE_SOURCES, config, gateway, REAL_PROMPTS,
    )

    assert failed is False and score is not None
    prompt = trace_events(trace_path)[0]["prompt"]
    assert prompt.count("Creatinine 1.1 mg/dL, eGFR 78.") == 1
    assert "### CASE-tests\nCreatinine 1.1 mg/dL, eGFR 78." in prompt
