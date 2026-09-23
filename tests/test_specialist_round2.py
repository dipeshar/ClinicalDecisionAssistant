"""Specialist Round 2: other arguments, own checks, judge notes (no scores), revisions,
rebuttal targeting, and the binding-judge-concern override. FakeProvider only.
"""

import json
from pathlib import Path

from council.agents import specialist as s
from council.budget import Budget
from council.gateway import LLMGateway
from council.kb import KnowledgeBase
from council.models import (
    CaseSection, CaseContext, Citation, Claim, Argument, Config, FeedbackNote, Passage, Role, Score,
    UntraceableClaim,
)
from council.providers.fake import FakeProvider, Scripted
from council.trace import TraceWriter

REAL_PROMPTS = Path("prompts")


def case_context() -> CaseContext:
    sections = [
        CaseSection(id="CASE-diagnoses", heading="Diagnoses and History",
                   text="Synthetic case for a demonstration. Chronic condition under stable management.",
                   flagged=False, flag_reasons=[]),
        CaseSection(id="CASE-comorbidities", heading="Comorbidities", text="No major comorbidities noted.",
                   flagged=False, flag_reasons=[]),
        CaseSection(id="CASE-tests", heading="Tests and Imaging", text="Creatinine 1.1 mg/dL, eGFR 78.",
                   flagged=False, flag_reasons=[]),
        CaseSection(id="CASE-procedure", heading="Proposed Procedure", text="Elective synthetic procedure proposed.",
                   flagged=False, flag_reasons=[]),
        CaseSection(id="CASE-consultant-review", heading="Consultant Review", text="No prior consultant review.",
                   flagged=False, flag_reasons=[]),
    ]
    return CaseContext(case_id="synthetic01", source_file="cases/synthetic01.md", case_hash="a" * 64,
                       title="Synthetic exercise", sections=sections, missing_sections=[], injection_flags=[])


def knowledge_base() -> KnowledgeBase:
    passage = Passage(id="SURG-KB-01", kb="surgeon", source_title="Synthetic summary",
                      text="Operative risk is low when renal function is normal and no major "
                           "comorbidities are present in this synthetic patient population.")
    return KnowledgeBase({Role.SURG: [passage]})


def own_round1(claim_count: int = 2) -> Argument:
    claims = [
        Claim(claim_id=f"R1-SURG-C{i}", text=f"Synthetic claim {i}.",
             citations=[Citation(passage_id="SURG-KB-01", quote="Operative risk is low when renal function is normal",
                                source_type="kb", verified=True, verify_note="")],
             grounding_status="grounded")
        for i in range(1, claim_count + 1)
    ]
    return Argument(argument_id="R1-SURG", role=Role.SURG, round=1, stance="for", summary="Synthetic summary.",
                    claims=claims, conditions=[], uncertainties=[], rebuttal=None, revisions=None,
                    stance_changed=False, retrieved_passage_ids=["SURG-KB-01"], repair_used=False,
                    status="ok", failure_reason=None)


def other_round1(role: Role, status: str = "ok") -> Argument:
    argument_id = f"R1-{role.value}"
    if status == "failed":
        return Argument(argument_id=argument_id, role=role, round=1, stance=None, summary="",
                        claims=[], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
                        stance_changed=False, retrieved_passage_ids=[], repair_used=False,
                        status="failed", failure_reason="Synthetic failure")
    claim = Claim(claim_id=f"{argument_id}-C1", text="Synthetic opposing claim.", citations=[], grounding_status="ungrounded")
    return Argument(argument_id=argument_id, role=role, round=1, stance="against", summary="Synthetic opposing view.",
                    claims=[claim], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
                    stance_changed=False, retrieved_passage_ids=[], repair_used=False,
                    status="ok", failure_reason=None)


ALL_ROUND1 = [own_round1(), other_round1(Role.PHYS), other_round1(Role.ANAES), other_round1(Role.ADMIN)]


def revision(claim_id: str, action: str, index: int | None) -> dict:
    return {"round1_claim_id": claim_id, "action": action, "new_claim_index": index, "reason": "Synthetic reason."}


_USE_DEFAULT_REBUTTAL = object()


def round2_json(revisions: list[dict], claims: list[dict] | None = None, rebuttal: object = _USE_DEFAULT_REBUTTAL) -> str:
    default_claim = {"text": "Renal function remains normal on review.",
                     "citations": [{"passage_id": "SURG-KB-01",
                                   "quote": "Operative risk is low when renal function is normal"}]}
    default_rebuttal = {
        "target_argument_id": "R1-PHYS", "target_claim_id": "R1-PHYS-C1",
        "why_strongest": "It is the clearest opposing claim.",
        "response_claims": [{"text": "The opposing claim overstates the risk.",
                            "citations": [{"passage_id": "SURG-KB-01",
                                          "quote": "Operative risk is low when renal function is normal"}]}],
    }
    return json.dumps({
        "stance": "for", "summary": "Synthetic Round 2 position.",
        "claims": claims if claims is not None else [default_claim],
        "conditions": [], "uncertainties": [],
        "rebuttal": default_rebuttal if rebuttal is _USE_DEFAULT_REBUTTAL else rebuttal,
        "revisions": revisions,
    })


def make_gateway(config: Config, tmp_path: Path, script: list) -> tuple[LLMGateway, Path]:
    provider = FakeProvider("fake", script)
    budget = Budget(config.budget)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, "run-round2-synthetic")
    return LLMGateway(config, budget, trace, {"fake": provider}, sleep_fn=lambda seconds: None), trace_path


def trace_events(trace_path: Path) -> list[dict]:
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]


def test_good_output_produces_an_ok_round2_argument(config: Config, tmp_path: Path) -> None:
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(revisions), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None
    assert argument.status == "ok" and argument.failure_reason is None
    assert argument.argument_id == "R2-SURG" and argument.round == 2
    assert len(argument.claims) == 1 and argument.claims[0].grounding_status == "grounded"
    assert argument.claims[0].claim_id == "R2-SURG-C1"
    assert argument.rebuttal is not None
    assert argument.rebuttal.target_argument_id == "R1-PHYS" and argument.rebuttal.target_claim_id == "R1-PHYS-C1"
    assert len(argument.rebuttal.response_claims) == 1
    assert argument.rebuttal.response_claims[0].grounding_status == "grounded"
    # Rebuttal claims continue the same claim_id numbering after the main claims list.
    assert argument.rebuttal.response_claims[0].claim_id == "R2-SURG-C2"
    assert {r.round1_claim_id for r in argument.revisions} == {"R1-SURG-C1", "R1-SURG-C2"}
    kept = next(r for r in argument.revisions if r.round1_claim_id == "R1-SURG-C1")
    assert kept.action == "kept" and kept.new_claim_id == "R2-SURG-C1"
    dropped = next(r for r in argument.revisions if r.round1_claim_id == "R1-SURG-C2")
    assert dropped.action == "dropped" and dropped.new_claim_id is None
    assert argument.stance_changed is False

    prompt = trace_events(trace_path)[0]["prompt"]
    assert "R1-PHYS" in prompt and "R1-ANAES" in prompt and "R1-ADMIN" in prompt  # other arguments
    assert "### R1-PHYS (PHYS)" in prompt  # the "other argument" heading format
    assert "### R1-SURG (SURG)" not in prompt  # own role must not appear as an "other" argument
    assert "----- BEGIN Your Round 1 argument" in prompt  # the labeled data block itself
    assert "R1-SURG-C1" in prompt and "R1-SURG-C2" in prompt
    assert "SURG-KB-01" in prompt and "Operative risk is low" in prompt  # retrieved passages block


def test_round1_failure_skips_round2(config: Config, tmp_path: Path) -> None:
    failed = other_round1(Role.SURG, status="failed")
    gateway, _ = make_gateway(config, tmp_path, [Scripted()])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            failed, ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is None


def test_judge_notes_never_include_scores(config: Config, tmp_path: Path) -> None:
    scores = [
        Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=1, logic=1, uncertainty=1, counterarguments=None,
             justification={"groundedness": "should never appear in the prompt"},
             untraceable_claims=[UntraceableClaim(claim_id="R1-SURG-C2", reason="Cannot trace this one.")],
             feedback=[FeedbackNote(claim_id="R1-SURG-C1", note="Consider a stronger citation.")]),
        Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=5, logic=5, uncertainty=5, counterarguments=None,
             justification={"groundedness": "also should never appear"}, untraceable_claims=[],
             feedback=[FeedbackNote(claim_id=None, note="General note with no claim.")]),
    ]
    revisions = [revision("R1-SURG-C1", "revised", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(revisions), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, scores, REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    prompt = trace_events(trace_path)[0]["prompt"]
    assert "Consider a stronger citation." in prompt
    assert "Cannot trace this one." in prompt
    assert "General note with no claim." in prompt
    assert "should never appear" not in prompt
    assert "groundedness" not in prompt.lower().split("## response schema")[0]


def test_missing_revision_fails_the_turn_if_still_missing_after_repair(config: Config, tmp_path: Path) -> None:
    incomplete = [revision("R1-SURG-C1", "kept", 1)]  # C2 never accounted for
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(incomplete), tokens_in=5, tokens_out=5),
        Scripted(raw_output=round2_json(incomplete), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None
    assert argument.status == "failed"
    assert argument.repair_used is True
    assert argument.claims == [] and argument.stance is None
    events = trace_events(trace_path)
    assert len(events) == 2


def test_missing_revision_recovers_after_repair(config: Config, tmp_path: Path) -> None:
    incomplete = [revision("R1-SURG-C1", "kept", 1)]
    complete = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(incomplete), tokens_in=5, tokens_out=5),
        Scripted(raw_output=round2_json(complete), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None
    assert argument.status == "ok" and argument.repair_used is True
    assert {r.round1_claim_id for r in argument.revisions} == {"R1-SURG-C1", "R1-SURG-C2"}


def test_rebuttal_targeting_own_role_triggers_repair(config: Config, tmp_path: Path) -> None:
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    bad_rebuttal = {"target_argument_id": "R1-SURG", "target_claim_id": "R1-SURG-C1",
                    "why_strongest": "Invalid: targets its own Round 1 argument.",
                    "response_claims": [{"text": "x", "citations": []}]}
    good_rebuttal = {"target_argument_id": "R1-PHYS", "target_claim_id": "R1-PHYS-C1",
                     "why_strongest": "It is the clearest opposing claim.",
                     "response_claims": [{"text": "The opposing claim overstates the risk.",
                                         "citations": [{"passage_id": "SURG-KB-01",
                                                       "quote": "Operative risk is low when renal function is normal"}]}]}
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(revisions, rebuttal=bad_rebuttal), tokens_in=5, tokens_out=5),
        Scripted(raw_output=round2_json(revisions, rebuttal=good_rebuttal), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    assert argument.rebuttal.target_argument_id == "R1-PHYS"
    events = trace_events(trace_path)
    assert [event["repair"] for event in events] == [False, True]


def test_no_rebuttal_fails_the_turn_if_still_missing_after_repair(config: Config, tmp_path: Path) -> None:
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    no_rebuttal = round2_json(revisions, rebuttal=None)
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=no_rebuttal, tokens_in=5, tokens_out=5),
        Scripted(raw_output=no_rebuttal, tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "failed"


def test_binding_judge_concern_kept_gets_overridden(config: Config, tmp_path: Path) -> None:
    """Both judges flag C1; the specialist keeps it anyway both times; code overrides it."""
    scores = [
        Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=2, logic=3, uncertainty=3, counterarguments=None, justification={},
             untraceable_claims=[UntraceableClaim(claim_id="R1-SURG-C1", reason="Doesn't support the claim.")],
             feedback=[]),
        Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=2, logic=3, uncertainty=3, counterarguments=None, justification={},
             untraceable_claims=[], feedback=[FeedbackNote(claim_id="R1-SURG-C1", note="Citation looks weak.")]),
    ]
    kept_anyway = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(kept_anyway), tokens_in=5, tokens_out=5),
        Scripted(raw_output=round2_json(kept_anyway), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, scores, REAL_PROMPTS)

    assert argument is not None
    assert argument.status == "ok"  # rule 24: does not fail the turn
    assert argument.repair_used is True
    overridden = next(r for r in argument.revisions if r.round1_claim_id == "R1-SURG-C1")
    assert overridden.action == "dropped" and overridden.new_claim_index is None and overridden.new_claim_id is None
    assert "both judges flagged" in overridden.reason.lower()
    assert argument.claims == []  # the only claim (index 1) was the overridden one
    events = trace_events(trace_path)
    validation_events = [event for event in events if event["event_type"] == "validation"]
    assert len(validation_events) == 1
    assert validation_events[0]["parsed_ref"] == "R1-SURG-C1"
    assert validation_events[0]["role"] == "SURG"


def test_binding_judge_concern_fixed_by_repair_needs_no_override(config: Config, tmp_path: Path) -> None:
    scores = [
        Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=2, logic=3, uncertainty=3, counterarguments=None, justification={},
             untraceable_claims=[UntraceableClaim(claim_id="R1-SURG-C1", reason="Doesn't support the claim.")],
             feedback=[]),
        Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=2, logic=3, uncertainty=3, counterarguments=None, justification={},
             untraceable_claims=[], feedback=[FeedbackNote(claim_id="R1-SURG-C1", note="Citation looks weak.")]),
    ]
    kept_anyway = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    fixed = [revision("R1-SURG-C1", "revised", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(kept_anyway), tokens_in=5, tokens_out=5),
        Scripted(raw_output=round2_json(fixed), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, scores, REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    revised = next(r for r in argument.revisions if r.round1_claim_id == "R1-SURG-C1")
    assert revised.action == "revised" and revised.new_claim_id == "R2-SURG-C1"
    events = trace_events(trace_path)
    assert not any(event["event_type"] == "validation" for event in events)


def test_binding_requires_both_judges_not_just_one(config: Config, tmp_path: Path) -> None:
    """Only JUDGE_A flags C1; keeping it is fine, no repair, no override."""
    scores = [
        Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=2, logic=3, uncertainty=3, counterarguments=None, justification={},
             untraceable_claims=[UntraceableClaim(claim_id="R1-SURG-C1", reason="Doesn't support the claim.")],
             feedback=[]),
        Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=5, logic=5, uncertainty=5, counterarguments=None, justification={},
             untraceable_claims=[], feedback=[]),
    ]
    kept = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [Scripted(raw_output=round2_json(kept), tokens_in=5, tokens_out=5)])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, scores, REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    assert argument.repair_used is False
    kept_revision = next(r for r in argument.revisions if r.round1_claim_id == "R1-SURG-C1")
    assert kept_revision.action == "kept" and kept_revision.new_claim_id == "R2-SURG-C1"
    events = trace_events(trace_path)
    assert not any(event["event_type"] == "validation" for event in events)


def test_no_claims_kept_fails_the_turn_if_still_empty_after_repair(config: Config, tmp_path: Path) -> None:
    revisions = [revision("R1-SURG-C1", "dropped", None), revision("R1-SURG-C2", "dropped", None)]
    empty = round2_json(revisions, claims=[])
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=empty, tokens_in=5, tokens_out=5),
        Scripted(raw_output=empty, tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "failed"


def test_bad_json_twice_fails_the_turn(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output="not valid json"),
        Scripted(raw_output="still not valid json"),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "failed"


def test_failed_other_argument_excluded_from_prompt(config: Config, tmp_path: Path) -> None:
    round1_with_a_failure = [own_round1(), other_round1(Role.PHYS), other_round1(Role.ANAES, status="failed"),
                             other_round1(Role.ADMIN)]
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(revisions), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), round1_with_a_failure, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    prompt = trace_events(trace_path)[0]["prompt"]
    assert "### R1-PHYS (PHYS)" in prompt
    assert "### R1-ANAES (ANAES)" not in prompt


def test_judge_notes_filter_to_own_round1_argument(config: Config, tmp_path: Path) -> None:
    """A score for a different argument, or a different round, must not appear in the notes."""
    scores = [
        Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
             groundedness=5, logic=5, uncertainty=5, counterarguments=None, justification={},
             untraceable_claims=[], feedback=[FeedbackNote(claim_id=None, note="Relevant note for SURG.")]),
        Score(judge="JUDGE_A", argument_id="R1-PHYS", model="fake/judge", round=1,
             groundedness=1, logic=1, uncertainty=1, counterarguments=None, justification={},
             untraceable_claims=[], feedback=[FeedbackNote(claim_id=None, note="Irrelevant note for PHYS.")]),
        Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=2,
             groundedness=1, logic=1, uncertainty=1, counterarguments=4, justification={},
             untraceable_claims=[], feedback=[]),
    ]
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=round2_json(revisions), tokens_in=5, tokens_out=5),
    ])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, scores, REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    prompt = trace_events(trace_path)[0]["prompt"]
    assert "Relevant note for SURG." in prompt
    assert "Irrelevant note for PHYS." not in prompt


def test_stance_changed_is_recorded_when_stance_differs(config: Config, tmp_path: Path) -> None:
    revisions = [revision("R1-SURG-C1", "kept", 1), revision("R1-SURG-C2", "dropped", None)]
    changed = json.loads(round2_json(revisions))
    changed["stance"] = "against"
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=json.dumps(changed), tokens_in=5, tokens_out=5)])

    argument = s.run_round2(Role.SURG, case_context(), knowledge_base(), config, gateway,
                            own_round1(), ALL_ROUND1, [], REAL_PROMPTS)

    assert argument is not None and argument.status == "ok"
    assert argument.stance == "against"
    assert argument.stance_changed is True


def test_render_other_arguments_excludes_own_role() -> None:
    others = [other_round1(Role.PHYS), other_round1(Role.ANAES)]
    text = s.render_other_arguments(others)
    assert "R1-PHYS" in text and "R1-ANAES" in text and "R1-SURG" not in text


def test_render_other_arguments_handles_none_available() -> None:
    assert s.render_other_arguments([]) == "(no other Round 1 arguments are available)"


def test_binding_claim_ids_requires_both_judges() -> None:
    one_judge = [Score(judge="JUDGE_A", argument_id="R1-SURG", model="fake/judge", round=1,
                       groundedness=1, logic=1, uncertainty=1, counterarguments=None, justification={},
                       untraceable_claims=[UntraceableClaim(claim_id="R1-SURG-C1", reason="x")], feedback=[])]
    assert s.binding_claim_ids(one_judge) == set()

    both_judges = one_judge + [Score(judge="JUDGE_B", argument_id="R1-SURG", model="fake/judge", round=1,
                                     groundedness=1, logic=1, uncertainty=1, counterarguments=None, justification={},
                                     untraceable_claims=[], feedback=[FeedbackNote(claim_id="R1-SURG-C1", note="x")])]
    assert s.binding_claim_ids(both_judges) == {"R1-SURG-C1"}
