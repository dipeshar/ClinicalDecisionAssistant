"""Specialist Round 1: retrieval, gateway call, parse, repair, grounding. FakeProvider only."""

import json
from pathlib import Path

from council.agents import specialist as s
from council.budget import Budget
from council.gateway import LLMGateway
from council.kb import KnowledgeBase
from council.models import CaseSection, CaseContext, Config, Passage, Role, ScoreDraft
from council.providers.base import ProviderError
from council.providers.fake import FakeProvider, Scripted
from council.trace import TraceWriter

REAL_PROMPTS = Path("prompts")

GOOD_JSON = """{
  "stance": "for",
  "summary": "The evidence supports proceeding given normal renal function.",
  "claims": [
    {"text": "Renal function is normal, supporting a low operative risk.",
     "citations": [{"passage_id": "SURG-KB-01", "quote": "Operative risk is low when renal function is normal"}]}
  ],
  "conditions": [],
  "uncertainties": [],
  "rebuttal": null,
  "revisions": null
}"""

BAD_CITATION_JSON = """{
  "stance": "for",
  "summary": "The evidence supports proceeding.",
  "claims": [
    {"text": "Renal function is abnormal and risky for this procedure.",
     "citations": [{"passage_id": "SURG-KB-01", "quote": "renal function is definitely abnormal and risky"}]}
  ],
  "conditions": [],
  "uncertainties": [],
  "rebuttal": null,
  "revisions": null
}"""

ZERO_CITATION_JSON = """{
  "stance": "for",
  "summary": "The evidence supports proceeding.",
  "claims": [
    {"text": "Renal function is normal.", "citations": []}
  ],
  "conditions": [],
  "uncertainties": [],
  "rebuttal": null,
  "revisions": null
}"""

CASE_CITATION_JSON = """{
  "stance": "for",
  "summary": "The evidence supports proceeding given a normal creatinine reading.",
  "claims": [
    {"text": "Renal function markers are within normal range for this patient.",
     "citations": [{"passage_id": "CASE-tests", "quote": "Creatinine 1.1 mg/dL, eGFR 78"}]}
  ],
  "conditions": [],
  "uncertainties": [],
  "rebuttal": null,
  "revisions": null
}"""

BAD_JSON = "not valid json {{{"

# A real response from qwen/qwen3.8-27b (run-20260926-112051-cardiac-01, trace
# seq 10, JUDGE_A scoring R1-PHYS in Round 1) -- this model wraps every Round 1
# judge response in a ```json fence, which `parse_draft` used to send straight
# to `model_validate_json` unstripped, failing every single one of these calls
# regardless of content or token budget.
REAL_FENCED_JUDGE_RESPONSE = """```json
{
  "argument_id": "R1-PHYS",
  "groundedness": 5,
  "logic": 5,
  "uncertainty": 5,
  "counterarguments": null,
  "justification": {
    "groundedness": "All four claims cite sources that directly and clearly support them. C1's 'accelerates the need for intervention' maps to PHYS-KB-02's 'accelerates the timeline for considering intervention.' C2's 'conservative management unlikely to be adequate' is nearly verbatim from PHYS-KB-04. C3 and C4 are direct restatements of their cited passages. No citation is misused or overstretched.",
    "logic": "The four claims establish that intervention is necessary (C1–C4), the summary then identifies the surgical option as addressing both lesions, and the conditional stance with three explicit conditions follows naturally from the acknowledged renal and contrast-allergy uncertainties. No internal contradictions.",
    "uncertainty": "Three specific uncertainties are named (dialysis probability, TAVI contrast-sparing feasibility, long-term valve durability), and each maps to a corresponding condition. The conditional stance is appropriately calibrated to the gaps in the evidence."
  },
  "untraceable_claims": [],
  "feedback": [
    {
      "claim_id": null,
      "note": "The summary asserts 'Surgery with CABG would address both lesions' without a formal citation. Consider citing CASE-procedure or CASE-consultant-review to ground this explicitly."
    },
    {
      "claim_id": null,
      "note": "The patient's stated fear of dialysis is flagged by the cardiologist as 'directly relevant to consent.' The argument acknowledges renal risk but does not explicitly integrate the patient's values into the conditional framework."
    },
    {
      "claim_id": null,
      "note": "The argument does not address why leaving the 70% proximal LAD stenosis unaddressed (as in a TAVI-first strategy) would be clinically problematic. A brief note on this would strengthen the conditional logic."
    },
    {
      "claim_id": null,
      "note": "Condition 1 says 'acceptable level' for dialysis risk without defining what that threshold is. Even a rough framing (e.g., 'below X%') would make the condition more actionable for the council."
    }
  ]
}
```"""


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


def make_gateway(config: Config, tmp_path: Path, script: list) -> tuple[LLMGateway, Path]:
    provider = FakeProvider("fake", script)
    budget = Budget(config.budget)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, "run-specialist-synthetic")
    return LLMGateway(config, budget, trace, {"fake": provider}, sleep_fn=lambda seconds: None), trace_path


def trace_events(trace_path: Path) -> list[dict]:
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]


def test_parse_draft_strips_a_real_fenced_judge_response() -> None:
    """The exact real fenced response that failed every Round 1 judge call in
    run-20260926-112051-cardiac-01 must now parse successfully."""
    draft, error = s.parse_draft(REAL_FENCED_JUDGE_RESPONSE, ScoreDraft)
    assert error is None
    assert draft is not None
    assert draft.argument_id == "R1-PHYS"
    assert draft.groundedness == 5
    assert len(draft.feedback) == 4


def test_parse_draft_fenced_and_unfenced_equivalents_parse_identically() -> None:
    """Stripping the fence must not change the parsed content: the same real
    response, with only the wrapping ```json / ``` lines removed by hand,
    parses to the exact same draft."""
    unfenced = REAL_FENCED_JUDGE_RESPONSE.removeprefix("```json\n").removesuffix("\n```")
    assert unfenced != REAL_FENCED_JUDGE_RESPONSE  # sanity: the fence really was there to remove

    fenced_draft, fenced_error = s.parse_draft(REAL_FENCED_JUDGE_RESPONSE, ScoreDraft)
    unfenced_draft, unfenced_error = s.parse_draft(unfenced, ScoreDraft)

    assert fenced_error is None
    assert unfenced_error is None
    assert fenced_draft == unfenced_draft


def test_parse_draft_leaves_an_unclosed_fence_alone() -> None:
    """A response with only an opening fence and no closing one is NOT
    stripped -- guessing at a truncated/partial fence risks corrupting real
    content, so this must fail to parse exactly as it did before the fix,
    not be silently patched into something that happens to validate."""
    unclosed = '```json\n{"argument_id": "R1-SURG", "groundedness": 3'
    draft, error = s.parse_draft(unclosed, ScoreDraft)
    assert draft is None
    assert error is not None
    # confirms strip_code_fence itself left the text untouched, not just that
    # parsing failed for some other reason
    assert s.strip_code_fence(unclosed) == unclosed


def test_strip_code_fence_leaves_unfenced_content_unchanged() -> None:
    assert s.strip_code_fence(GOOD_JSON) == GOOD_JSON


def test_good_output_produces_a_grounded_ok_argument(config: Config, tmp_path: Path) -> None:
    gateway, trace_path = make_gateway(config, tmp_path, [Scripted(raw_output=GOOD_JSON, tokens_in=5, tokens_out=5)])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    prompt = trace_events(trace_path)[0]["prompt"]
    assert "----- BEGIN Case" in prompt and "Creatinine 1.1 mg/dL, eGFR 78." in prompt
    assert "----- BEGIN Retrieved passages" in prompt and "SURG-KB-01" in prompt

    assert argument.status == "ok" and argument.failure_reason is None
    assert argument.repair_used is False
    assert argument.argument_id == "R1-SURG" and argument.role == Role.SURG and argument.round == 1
    assert argument.stance == "for"
    assert len(argument.claims) == 1
    claim = argument.claims[0]
    assert claim.claim_id == "R1-SURG-C1"
    assert claim.grounding_status == "grounded"
    assert claim.citations[0].verified is True
    assert argument.retrieved_passage_ids == ["SURG-KB-01"]
    assert argument.rebuttal is None and argument.revisions is None
    assert argument.stance_changed is False


def test_bad_json_then_fixed_uses_the_repair_retry(config: Config, tmp_path: Path) -> None:
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=BAD_JSON),
        Scripted(raw_output=GOOD_JSON, tokens_in=5, tokens_out=5),
    ])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "ok"
    assert argument.repair_used is True
    assert argument.stance == "for"
    assert argument.claims[0].grounding_status == "grounded"
    events = trace_events(trace_path)
    assert len(events) == 2
    assert [event["repair"] for event in events] == [False, True]
    # design.md, "LLM gateway": a repair call resends the exact same user
    # message (data plus schema) unchanged; only system grows.
    users = [event["prompt"].split("[USER]\n", 1)[1] for event in events]
    systems = [event["prompt"].split("[USER]\n", 1)[0] for event in events]
    assert users[0] == users[1]
    assert systems[0] != systems[1] and systems[0] in systems[1]


def test_bad_json_twice_fails_the_turn(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=BAD_JSON),
        Scripted(raw_output=BAD_JSON),
    ])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "failed"
    assert argument.repair_used is True
    assert argument.stance is None
    assert argument.claims == [] and argument.conditions == [] and argument.uncertainties == []
    assert argument.rebuttal is None and argument.revisions is None
    assert argument.failure_reason
    assert argument.retrieved_passage_ids == ["SURG-KB-01"]


def test_bad_citation_twice_leaves_the_claim_ungrounded_but_the_turn_ok(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=BAD_CITATION_JSON, tokens_in=5, tokens_out=5),
        Scripted(raw_output=BAD_CITATION_JSON, tokens_in=5, tokens_out=5),
    ])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "ok"
    assert argument.repair_used is True
    assert len(argument.claims) == 1
    claim = argument.claims[0]
    assert claim.grounding_status == "ungrounded"
    assert claim.citations[0].verified is False
    assert claim.citations[0].verify_note == "quote text not found in source in order"


def test_bad_citation_then_fixed_grounds_the_claim(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [
        Scripted(raw_output=BAD_CITATION_JSON, tokens_in=5, tokens_out=5),
        Scripted(raw_output=GOOD_JSON, tokens_in=5, tokens_out=5),
    ])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "ok"
    assert argument.repair_used is True
    assert argument.claims[0].grounding_status == "grounded"


def test_claim_citing_a_case_section_is_grounded(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=CASE_CITATION_JSON, tokens_in=5, tokens_out=5)])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "ok"
    assert argument.claims[0].grounding_status == "grounded"
    citation = argument.claims[0].citations[0]
    assert citation.passage_id == "CASE-tests" and citation.source_type == "case" and citation.verified is True


def test_claim_with_no_citation_is_ungrounded_and_triggers_repair(config: Config, tmp_path: Path) -> None:
    gateway, trace_path = make_gateway(config, tmp_path, [
        Scripted(raw_output=ZERO_CITATION_JSON, tokens_in=5, tokens_out=5),
        Scripted(raw_output=ZERO_CITATION_JSON, tokens_in=5, tokens_out=5),
    ])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "ok"
    assert argument.repair_used is True
    assert argument.claims[0].grounding_status == "ungrounded"
    assert argument.claims[0].citations == []
    events = trace_events(trace_path)
    assert "no citation was given" in events[1]["prompt"]


def test_gateway_refusal_on_first_call_fails_the_turn_without_a_repair(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [ProviderError])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "failed"
    assert argument.repair_used is False
    assert "gateway refused" in (argument.failure_reason or "")


def test_settlement_overrun_fails_the_turn_instead_of_escaping(
    config: Config, tmp_path: Path,
) -> None:
    gateway, trace_path = make_gateway(config, tmp_path, [Scripted(
        raw_output=GOOD_JSON, tokens_in=1_000_000, tokens_out=5,
    )])

    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "failed"
    assert argument.repair_used is False
    assert "actual usage exceeds the reserved bounds" in (argument.failure_reason or "")
    event = trace_events(trace_path)[0]
    assert event["error"].startswith(
        "actual usage exceeds the reserved bounds: input actual=1000000, reserved="
    )


def test_gateway_refusal_on_repair_call_still_marks_repair_used(config: Config, tmp_path: Path) -> None:
    gateway, _ = make_gateway(config, tmp_path, [Scripted(raw_output=BAD_JSON), ProviderError])
    argument = s.run_round1(Role.SURG, case_context(), knowledge_base(), config, gateway, REAL_PROMPTS)

    assert argument.status == "failed"
    assert argument.repair_used is True
    assert "gateway refused the repair attempt" in (argument.failure_reason or "")


def test_render_case_labels_every_section_with_its_id() -> None:
    text = s.render_case(case_context())
    assert "## Diagnoses and History (CASE-diagnoses)" in text
    assert "Creatinine 1.1 mg/dL, eGFR 78." in text


def test_render_passages_labels_every_passage_with_its_id() -> None:
    text = s.render_passages(knowledge_base().passages[Role.SURG])
    assert "## SURG-KB-01 — Synthetic summary" in text


def test_render_passages_handles_no_passages_retrieved() -> None:
    assert s.render_passages([]) == "(no passages were retrieved)"
