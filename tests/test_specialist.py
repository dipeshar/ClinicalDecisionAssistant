"""Specialist Round 1: retrieval, gateway call, parse, repair, grounding. FakeProvider only."""

import json
from pathlib import Path

from council.agents import specialist as s
from council.budget import Budget
from council.gateway import LLMGateway
from council.kb import KnowledgeBase
from council.models import CaseSection, CaseContext, Config, Passage, Role
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
