"""Contract fixtures are synthetic; no provider or model calls are needed."""

from copy import deepcopy
from enum import StrEnum
import json
from typing import Any

import pytest
from pydantic import ValidationError

from council import models as m


def contract_samples() -> dict[str, dict[str, Any]]:
    """Explicit wire examples, including every declared nested object."""
    s: dict[str, dict[str, Any]] = {}
    s["InjectionFlag"] = dict(section_id="CASE-tests", line_number=2, matched_pattern="instruction")
    s["CaseSection"] = dict(id="CASE-tests", heading="Tests and Imaging", text="Synthetic data only.",
                            flagged=True, flag_reasons=["instruction"])
    s["CaseContext"] = dict(case_id="synthetic01", source_file="cases/synthetic01.md", case_hash="a" * 64,
                            title="Synthetic exercise", sections=[s["CaseSection"]],
                            missing_sections=["Allergies"], injection_flags=[s["InjectionFlag"]])
    s["Passage"] = dict(id="SURG-KB-01", kb="surgeon", source_title="Synthetic summary",
                        text="Synthetic passage for contract tests.")
    s["RetrievalResult"] = dict(role="SURG", round=1, query="synthetic", passages=[s["Passage"]], scores=[1.5])
    s["CitationDraft"] = dict(passage_id="CASE-tests", quote="Synthetic quotation for this test")
    s["Citation"] = dict(**s["CitationDraft"], source_type="case", verified=False, verify_note="quote not found")
    s["ClaimDraft"] = dict(text="Synthetic claim", citations=[s["CitationDraft"]])
    s["Claim"] = dict(claim_id="R1-SURG-C1", text="Synthetic claim", citations=[s["Citation"]],
                      grounding_status="ungrounded")
    s["RebuttalDraft"] = dict(target_argument_id="R1-PHYS", target_claim_id="R1-PHYS-C1",
                              why_strongest="Synthetic opposition", response_claims=[s["ClaimDraft"]])
    s["Rebuttal"] = dict(s["RebuttalDraft"], response_claims=[s["Claim"]])
    s["RevisionDraft"] = dict(round1_claim_id="R1-SURG-C1", action="revised", new_claim_index=1,
                              reason="Responds to missing source")
    s["Revision"] = dict(**s["RevisionDraft"], new_claim_id="R2-SURG-C1")
    s["ArgumentDraft"] = dict(stance="conditional", summary="Synthetic decision support; needs clinical sign-off.",
                              claims=[s["ClaimDraft"]], conditions=["Review synthetic evidence"],
                              uncertainties=["Synthetic unknown"], rebuttal=None, revisions=None)
    s["Argument"] = dict(s["ArgumentDraft"], argument_id="R1-SURG", role="SURG", round=1,
                         claims=[s["Claim"]], stance_changed=False, retrieved_passage_ids=["SURG-KB-01"],
                         repair_used=False, status="ok", failure_reason=None)
    s["UntraceableClaim"] = dict(claim_id="R1-SURG-C1", reason="Missing source")
    s["FeedbackNote"] = dict(claim_id="R1-SURG-C1", note="Find a source")
    s["ScoreDraft"] = dict(groundedness=1, logic=3, uncertainty=5, counterarguments=None,
                           justification=dict(groundedness="No source", logic="Coherent", uncertainty="Explicit"),
                           untraceable_claims=[s["UntraceableClaim"]], feedback=[s["FeedbackNote"]])
    s["Score"] = dict(**s["ScoreDraft"], judge="JUDGE_A", argument_id="R1-SURG", model="fake-judge", round=1)
    s["FailedJudgeCall"] = dict(judge="JUDGE_B", round=1)
    s["CriterionMeans"] = dict(groundedness=1.0, logic=3.0, uncertainty=5.0, counterarguments=None)
    s["CriterionGaps"] = dict(groundedness=None, logic=None, uncertainty=None, counterarguments=None)
    s["ArgumentScoreSummary"] = dict(argument_id="R1-SURG", role="SURG", round=1, judges_scored=["JUDGE_A"],
                                      mean=s["CriterionMeans"], gap=s["CriterionGaps"], disagreement_count=0)
    s["RoundMeans"] = dict(round1=3.0, round2=None)
    s["SharedScore"] = dict(**s["RoundMeans"], change=None)
    s["UngroundedCounts"] = dict(round1=1, round2=None)
    s["RevisionCounts"] = dict(kept=0, revised=0, dropped=0)
    s["RoundComparison"] = dict(role="SURG", shared_score=s["SharedScore"], ungrounded_claims=s["UngroundedCounts"],
                                revisions=s["RevisionCounts"], round2_status="failed")
    s["Scorecard"] = dict(run_id="run-20260919-1030-synthetic01", scores=[s["Score"]],
                          presented_order={"JUDGE_A-R1": ["R1-SURG"]}, skipped_arguments=["R1-PHYS"],
                          failed_judge_calls=[s["FailedJudgeCall"]], per_argument=[s["ArgumentScoreSummary"]],
                          code_ungrounded_claims=["R1-SURG-C1"], round_comparison=[s["RoundComparison"]])
    s["RedTeamFindingDraft"] = dict(category="missing_info", severity="low", description="Synthetic missing source",
                                    evidence_ids=["CASE-tests"], affected_roles=["SURG"], suggested_action="Human review")
    s["RedTeamFinding"] = dict(**s["RedTeamFindingDraft"], finding_id="RT-1")
    s["InjectionCheckDraft"] = dict(verdict="no_sign", notes="Synthetic exercise")
    s["InjectionCheck"] = dict(**s["InjectionCheckDraft"], scanner_flag_count=1, claims_citing_flagged_lines=[])
    s["RedTeamReportDraft"] = dict(findings=[s["RedTeamFindingDraft"]], injection_check=s["InjectionCheckDraft"])
    s["RedTeamReport"] = dict(findings=[s["RedTeamFinding"]], injection_check=s["InjectionCheck"])
    s["Penalty"] = dict(count=1, penalty=5.0)
    s["ConfidenceInputs"] = dict(judge_part=50.0, judge_round_used=1, agreement_part=100.0,
                                 specialists_counted=1, specialists_accepting=1, base=75.0,
                                 ungrounded_claims=s["Penalty"], high_severity_findings=dict(count=0, penalty=0.0),
                                 judge_disagreements=dict(count=0, penalty=0.0), total_penalty=5.0)
    s["Confidence"] = dict(level="high", score=70.0, inputs=s["ConfidenceInputs"])
    s["JudgeParticipation"] = dict(judge="JUDGE_A", model="fake-judge", rounds_scored=[1])
    s["JudgeSummary"] = dict(mean_score=s["RoundMeans"], disagreement_count=0, judges=[s["JudgeParticipation"]],
                             failed_judge_calls=[s["FailedJudgeCall"]], round_comparison=[s["RoundComparison"]],
                             code_ungrounded_claims=["R1-SURG-C1"])
    s["RequiredAction"] = dict(text="Review synthetic source", source_ids=["RT-1"])
    s["Dissent"] = dict(role="SURG", stance="conditional", argument_id="R1-SURG", note="Synthetic dissent")
    s["HumanDecision"] = dict(run_id=s["Scorecard"]["run_id"], decision="comment_only", comment="Synthetic review",
                              reviewer="Fictional Reviewer", decided_at="2026-09-19T10:30:00Z", report_hash="b" * 64)
    s["ReportDraft"] = dict(recommendation="proceed", recommendation_basis=["R1-SURG"], strongest_for=[],
                            strongest_against=[], required_actions=[s["RequiredAction"]],
                            role_notes={"SURG": "Synthetic dissent"}, narrative="Review needed. [RT-1]")
    s["Report"] = dict(**s["ReportDraft"], run_id=s["Scorecard"]["run_id"], case_id="synthetic01", status="INCOMPLETE",
                       incomplete_reasons=["JUDGE_B failed"], failed_turns=["JUDGE_B"], confidence=s["Confidence"],
                       council_warning="Synthetic majority dissent", dissent=[s["Dissent"]],
                       red_team_findings=[s["RedTeamFinding"]], injection_check=s["InjectionCheck"],
                       judge_summary=s["JudgeSummary"], citations_index=[s["Citation"]],
                       disclaimer="decision support only, requires human clinical sign-off, synthetic data",
                       human_decision=s["HumanDecision"])
    s["TraceEvent"] = dict(run_id=s["Scorecard"]["run_id"], seq=1, timestamp="2026-09-19T10:30:00Z", step="judge",
                           event_type="error", role="JUDGE_B", round=1, model="fake-judge", prompt="Synthetic data",
                           retrieved_passage_ids=None, raw_output="invalid json", parsed_ref=None,
                           tokens_in=10, tokens_out=2, latency_ms=1, attempt=2, repair=True,
                           budget_tokens_used=12, error="Invalid output")
    s["BudgetState"] = dict(tokens_used=12, calls_used=1, started_at=123.5, exhausted=False, reason=None)
    s["ModelChoice"] = dict(provider="fake", model="fake-model")
    s["ModelChoices"] = {role: s["ModelChoice"] for role in ["specialist", "chair", "red_team", "judge_a", "judge_b"]}
    s["RoleValues"] = dict(specialist=0.4, judge=0.0, red_team=0.5, chair=0.2)
    s["TokenCaps"] = dict(specialist=1500, judge=2500, red_team=2500, chair=3000)
    s["ChairReserve"] = dict(tokens=10000, seconds=60, calls=2)
    s["BudgetConfig"] = dict(max_total_tokens=200000, max_calls=40, max_seconds_total=600,
                             chair_reserve=s["ChairReserve"], max_tokens_per_call=s["TokenCaps"])
    s["RetryConfig"] = dict(max_repair_retries_per_turn=1, max_api_attempts=2, api_retry_wait_seconds=2.0)
    s["RetrievalConfig"] = dict(top_k=5, case_sections=["CASE-tests"])
    s["GroundingConfig"] = dict(quote_words_min=4, quote_words_max=40)
    s["JudgingConfig"] = dict(disagreement_gap=2, feedback_max_notes=5, feedback_max_words=40)
    s["PathsConfig"] = dict(cases="cases", runs="runs", prompts="prompts")
    s["RoleConfig"] = dict(name="Synthetic surgeon", kb="kb/surgeon", keywords=["risk"], persona_prompt="persona_surg.md")
    s["Config"] = dict(paths=s["PathsConfig"], models=s["ModelChoices"], temperature=s["RoleValues"],
                       budget=s["BudgetConfig"], retries=s["RetryConfig"], retrieval=s["RetrievalConfig"],
                       grounding=s["GroundingConfig"], judging=s["JudgingConfig"], roles={"SURG": s["RoleConfig"]})
    s["Source"] = dict(source_type="case", source_title="Tests and Imaging", text="Synthetic data only.")
    s["RunBundle"] = dict(run_id=s["Scorecard"]["run_id"], case_id="synthetic01", created_at="2026-09-19T10:30:00Z",
                          config_snapshot=s["Config"], case_context=s["CaseContext"], retrievals=[s["RetrievalResult"]],
                          arguments=[s["Argument"]], scorecard=s["Scorecard"], red_team=s["RedTeamReport"],
                          report=s["Report"], sources={"CASE-tests": s["Source"]})
    return s


SAMPLES = contract_samples()


def test_every_contract_has_a_sample() -> None:
    classes = {name for name, value in vars(m).items() if isinstance(value, type)
               and issubclass(value, m.ContractModel) and value is not m.ContractModel}
    assert classes == set(SAMPLES)


@pytest.mark.parametrize("name", SAMPLES)
def test_contract_round_trip_and_fields(name: str) -> None:
    cls = getattr(m, name)
    data = SAMPLES[name]
    assert set(cls.model_fields) == set(data)
    record = cls.model_validate_json(json.dumps(data))
    assert json.loads(record.model_dump_json()) == data
    assert cls.model_validate_json(record.model_dump_json()) == record
    assert set(cls.model_json_schema()["properties"]) == set(data)


@pytest.mark.parametrize("name", SAMPLES)
def test_extra_fields_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        getattr(m, name).model_validate(dict(SAMPLES[name], invented_field="not in contract"))


@pytest.mark.parametrize("name,field", [
    (name, field) for name, data in SAMPLES.items() for field in data
    if (name, field) not in {("HumanDecision", "comment"), ("Report", "disclaimer"), ("RoleConfig", "persona_prompt")}
])
def test_required_fields(name: str, field: str) -> None:
    data = deepcopy(SAMPLES[name])
    del data[field]
    with pytest.raises(ValidationError, match="missing"):
        getattr(m, name).model_validate(data)


ENUMS = {
    "Role": "SURG PHYS ANAES ADMIN JUDGE_A JUDGE_B RED CHAIR",
    "Stance": "for against conditional", "SourceType": "case kb",
    "GroundingStatus": "grounded ungrounded", "RevisionAction": "kept revised dropped",
    "TurnStatus": "ok failed", "Round2Status": "ok failed skipped",
    "Criterion": "groundedness logic uncertainty counterarguments",
    "FindingCategory": "missing_info assumption contradiction overconfidence injection",
    "Level": "low medium high", "InjectionVerdict": "no_sign possible_influence influenced",
    "ReportStatus": "COMPLETE INCOMPLETE",
    "Recommendation": "proceed proceed_with_modifications delay_pending_investigation decline",
    "Decision": "approved rejected comment_only", "Step": "ingest retrieve specialist judge red_team chair human",
    "EventType": "start llm_call retrieval validation budget error decision",
}


@pytest.mark.parametrize("name,values", ENUMS.items())
def test_enum_values(name: str, values: str) -> None:
    enum = getattr(m, name)
    assert {value.value for value in enum} == set(values.split())
    with pytest.raises(ValueError):
        enum("INVALID")


def test_every_enum_is_checked() -> None:
    assert {name for name, value in vars(m).items() if isinstance(value, type)
            and issubclass(value, StrEnum) and value is not StrEnum} == set(ENUMS)


DRAFT_OWNERS = {
    "CitationDraft": "source_type verified verify_note",
    "ClaimDraft": "claim_id grounding_status",
    "RevisionDraft": "new_claim_id",
    "ArgumentDraft": "argument_id role round stance_changed retrieved_passage_ids repair_used status failure_reason",
    "ScoreDraft": "judge argument_id model round",
    "RedTeamFindingDraft": "finding_id",
    "InjectionCheckDraft": "scanner_flag_count claims_citing_flagged_lines",
    "ReportDraft": "run_id case_id status incomplete_reasons failed_turns confidence council_warning dissent red_team_findings injection_check judge_summary citations_index disclaimer human_decision",
}


@pytest.mark.parametrize("name,field", [(name, field) for name, fields in DRAFT_OWNERS.items() for field in fields.split()])
def test_drafts_reject_code_owned_fields(name: str, field: str) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        getattr(m, name).model_validate(dict(SAMPLES[name], **{field: None}))


@pytest.mark.parametrize("name,path,field", [
    ("ArgumentDraft", ("claims", 0), "grounding_status"),
    ("ArgumentDraft", ("claims", 0, "citations", 0), "verified"),
    ("RebuttalDraft", ("response_claims", 0), "claim_id"),
    ("RebuttalDraft", ("response_claims", 0, "citations", 0), "verified"),
    ("RedTeamReportDraft", ("findings", 0), "finding_id"),
    ("RedTeamReportDraft", ("injection_check",), "scanner_flag_count"),
])
def test_nested_drafts_reject_trust_fields(name: str, path: tuple[str | int, ...], field: str) -> None:
    data = deepcopy(SAMPLES[name])
    target = data
    for key in path:
        target = target[key]
    target[field] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        getattr(m, name).model_validate(data)


def test_draft_schemas_do_not_expose_code_fields() -> None:
    for name, fields in DRAFT_OWNERS.items():
        schema = getattr(m, name).model_json_schema()
        assert not (set(fields.split()) & set(schema["properties"]))
        assert schema["additionalProperties"] is False


def test_round2_argument_draft_round_trip() -> None:
    data = dict(SAMPLES["ArgumentDraft"], rebuttal=SAMPLES["RebuttalDraft"], revisions=[SAMPLES["RevisionDraft"]])
    assert json.loads(m.ArgumentDraft.model_validate(data).model_dump_json()) == data


@pytest.mark.parametrize("field,value", [
    ("revisions", [SAMPLES["Revision"]]), ("rebuttal", SAMPLES["Rebuttal"]),
])
def test_round2_draft_rejects_nested_full_records(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        m.ArgumentDraft.model_validate(dict(SAMPLES["ArgumentDraft"], **{field: value}))


@pytest.mark.parametrize("name,field", [
    ("Penalty", "penalty"), ("RoundMeans", "round1"), ("BudgetState", "started_at"),
])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_finite_numbers(name: str, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        getattr(m, name).model_validate(dict(SAMPLES[name], **{field: value}))


@pytest.mark.parametrize("field", ["groundedness", "logic", "uncertainty", "counterarguments"])
@pytest.mark.parametrize("value", [0, 6, 1.5, True, "3"])
def test_rating_bounds_and_integer_type(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        m.ScoreDraft.model_validate(dict(SAMPLES["ScoreDraft"], **{field: value}))


@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_all_rating_values(value: int) -> None:
    data = dict(SAMPLES["ScoreDraft"], groundedness=value, logic=value, uncertainty=value, counterarguments=value)
    assert m.ScoreDraft.model_validate(data).groundedness == value


@pytest.mark.parametrize("name,field", [
    ("Argument", "round"), ("RetrievalResult", "round"), ("Score", "round"),
    ("FailedJudgeCall", "round"), ("ArgumentScoreSummary", "round"),
    ("TraceEvent", "round"), ("TraceEvent", "attempt"), ("ConfidenceInputs", "judge_round_used"),
])
def test_two_rounds_and_attempts_only(name: str, field: str) -> None:
    with pytest.raises(ValidationError):
        getattr(m, name).model_validate(dict(SAMPLES[name], **{field: 3}))


@pytest.mark.parametrize("name", ["Score", "FailedJudgeCall", "JudgeParticipation"])
def test_judges_only(name: str) -> None:
    with pytest.raises(ValidationError):
        getattr(m, name).model_validate(dict(SAMPLES[name], judge="SURG"))


@pytest.mark.parametrize("action,index", [("kept", None), ("revised", None), ("dropped", 1), ("kept", 0)])
def test_revision_index_rules(action: str, index: int | None) -> None:
    with pytest.raises(ValidationError):
        m.RevisionDraft.model_validate(dict(SAMPLES["RevisionDraft"], action=action, new_claim_index=index))


@pytest.mark.parametrize("action,index", [("kept", 1), ("revised", 2), ("dropped", None)])
def test_valid_revision_actions(action: str, index: int | None) -> None:
    m.RevisionDraft.model_validate(dict(SAMPLES["RevisionDraft"], action=action, new_claim_index=index))


def failed_argument() -> dict[str, Any]:
    return deepcopy(dict(SAMPLES["Argument"], status="failed", stance=None, claims=[], conditions=[], uncertainties=[],
                         rebuttal=None, revisions=None, failure_reason="Invalid JSON after repair"))


def test_failed_argument_round_trip() -> None:
    data = failed_argument()
    record = m.Argument.model_validate(data)
    assert json.loads(record.model_dump_json()) == data


@pytest.mark.parametrize("field,value", [
    ("stance", "for"), ("claims", [SAMPLES["Claim"]]), ("conditions", ["condition"]),
    ("uncertainties", ["unknown"]), ("rebuttal", SAMPLES["Rebuttal"]), ("revisions", []),
    ("failure_reason", None), ("failure_reason", ""),
])
def test_failed_argument_rejects_content(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        m.Argument.model_validate(dict(failed_argument(), round=2, argument_id="R2-SURG", **{field: value}))


@pytest.mark.parametrize("field,value", [("stance", None), ("failure_reason", "failed")])
def test_ok_argument_requires_stance_and_no_failure(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        m.Argument.model_validate(dict(SAMPLES["Argument"], **{field: value}))


@pytest.mark.parametrize("field,value", [("rebuttal", SAMPLES["Rebuttal"]), ("revisions", [])])
def test_round1_has_no_rebuttal_or_revisions(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        m.Argument.model_validate(dict(SAMPLES["Argument"], **{field: value}))


def test_round2_argument_round_trip() -> None:
    data = deepcopy(SAMPLES["Argument"])
    data.update(argument_id="R2-SURG", round=2, rebuttal=SAMPLES["Rebuttal"], revisions=[SAMPLES["Revision"]])
    data["claims"][0]["claim_id"] = "R2-SURG-C1"
    assert json.loads(m.Argument.model_validate(data).model_dump_json()) == data


@pytest.mark.parametrize("round_number,counterarguments,feedback", [
    (1, 3, []), (2, None, []), (2, 3, [SAMPLES["FeedbackNote"]]),
])
def test_score_round_rules(round_number: int, counterarguments: int | None, feedback: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError):
        m.Score.model_validate(dict(SAMPLES["Score"], round=round_number,
                                    counterarguments=counterarguments, feedback=feedback))


def test_round2_score_round_trip() -> None:
    data = dict(SAMPLES["Score"], round=2, counterarguments=4, feedback=[])
    assert json.loads(m.Score.model_validate(data).model_dump_json()) == data


@pytest.mark.parametrize("name,field", [("Confidence", "score"), ("ConfidenceInputs", "judge_part"),
                                       ("ConfidenceInputs", "agreement_part")])
@pytest.mark.parametrize("value", [-0.1, 100.1, float("inf"), float("nan")])
def test_percentage_bounds(name: str, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        getattr(m, name).model_validate(dict(SAMPLES[name], **{field: value}))


@pytest.mark.parametrize("value", [0.0, 100.0])
def test_percentage_endpoints(value: float) -> None:
    m.Confidence.model_validate(dict(SAMPLES["Confidence"], score=value))


def bare_report() -> dict[str, Any]:
    return deepcopy(dict(SAMPLES["Report"], recommendation=None, confidence=None, council_warning=None,
                         recommendation_basis=[], strongest_for=[], strongest_against=[], required_actions=[],
                         dissent=[], role_notes={}, narrative="", human_decision=None))


def test_bare_report_round_trip() -> None:
    data = bare_report()
    assert json.loads(m.Report.model_validate(data).model_dump_json()) == data


@pytest.mark.parametrize("field,value", [
    ("status", "COMPLETE"), ("confidence", SAMPLES["Confidence"]), ("council_warning", "warning"),
    ("recommendation_basis", ["R1-SURG"]), ("strongest_for", ["R1-SURG-C1"]),
    ("strongest_against", ["R1-SURG-C1"]), ("required_actions", [SAMPLES["RequiredAction"]]),
    ("dissent", [SAMPLES["Dissent"]]), ("role_notes", {"SURG": "note"}), ("narrative", "invented"),
])
def test_bare_report_rejects_chair_content(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        m.Report.model_validate(dict(bare_report(), **{field: value}))


def test_non_bare_report_requires_confidence() -> None:
    with pytest.raises(ValidationError):
        m.Report.model_validate(dict(SAMPLES["Report"], confidence=None))


def test_fixed_disclaimer() -> None:
    with pytest.raises(ValidationError):
        m.Report.model_validate(dict(SAMPLES["Report"], disclaimer="automatically approved"))
    data = deepcopy(SAMPLES["Report"])
    del data["disclaimer"]
    assert m.Report.model_validate(data).disclaimer == SAMPLES["Report"]["disclaimer"]


def test_missing_evidence_can_be_preserved() -> None:
    claim = m.ClaimDraft(text="Needs a source", citations=[])
    assert claim.citations == []
    # T5 must see invalid quotes and IDs so it can repair/mark them ungrounded.
    assert m.CitationDraft(passage_id="unknown", quote="x").quote == "x"
    # T11 truncates feedback; the draft must first accept it without silent loss.
    notes = [dict(claim_id=None, note="word " * 41) for _ in range(6)]
    assert len(m.ScoreDraft.model_validate(dict(SAMPLES["ScoreDraft"], feedback=notes)).feedback) == 6


def test_no_judge_or_red_team_data_round_trip() -> None:
    data = deepcopy(SAMPLES["RunBundle"])
    data["red_team"] = None
    data["arguments"] = [failed_argument()]
    data["scorecard"].update(scores=[], per_argument=[], failed_judge_calls=[
        dict(judge="JUDGE_A", round=1), dict(judge="JUDGE_B", round=1)])
    data["report"] = bare_report()
    data["report"]["judge_summary"].update(mean_score=dict(round1=None, round2=None), judges=[])
    inputs = dict(SAMPLES["ConfidenceInputs"], judge_round_used=None, judge_part=0.0)
    assert m.ConfidenceInputs.model_validate(inputs).judge_round_used is None
    assert json.loads(m.RunBundle.model_validate(data).model_dump_json()) == data


def test_config_has_no_max_rounds() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        m.Config.model_validate(dict(SAMPLES["Config"], max_rounds=3))


def test_source_and_trace_text_is_preserved() -> None:
    text = '  Synthetic <script>alert("example")</script>\n  “quoted” — ...\ttext  '
    for name, field in [("CaseSection", "text"), ("Passage", "text"), ("Source", "text"),
                        ("TraceEvent", "prompt"), ("TraceEvent", "raw_output")]:
        cls = getattr(m, name)
        record = cls.model_validate(dict(SAMPLES[name], **{field: text}))
        assert getattr(cls.model_validate_json(record.model_dump_json()), field) == text


def test_optional_human_comment_and_red_persona() -> None:
    data = dict(SAMPLES["HumanDecision"])
    del data["comment"]
    assert m.HumanDecision.model_validate(data).comment == ""
    role = dict(SAMPLES["RoleConfig"])
    del role["persona_prompt"]
    assert m.RoleConfig.model_validate(role).persona_prompt is None
