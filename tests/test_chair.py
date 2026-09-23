"""T14 chair checks and report construction. FakeProvider only."""

import json
from pathlib import Path

from council.agents import chair
from council.budget import Budget
from council.gateway import LLMGateway
from council.models import (
    Argument, Citation, Claim, Config, FailedJudgeCall, InjectionCheck, JudgeSummary,
    Passage, PrivacySummary, RedTeamFinding, RedTeamReport, Role, RoundMeans,
    Score,
)
from council.providers.fake import FakeProvider, Scripted
from council.trace import TraceWriter

REAL_PROMPTS = Path("prompts")


def claim(argument_id: str, *, grounded: bool = True) -> Claim:
    return Claim(
        claim_id=f"{argument_id}-C1", text=f"Synthetic claim from {argument_id}.",
        citations=[Citation(passage_id="CASE-tests", quote="Synthetic tests support this council claim",
                            source_type="case", verified=grounded,
                            verify_note="" if grounded else "quote text not found")],
        grounding_status="grounded" if grounded else "ungrounded",
    )


def argument(role: Role, round_number: int, *, stance: str = "for", status: str = "ok",
             grounded: bool = True) -> Argument:
    argument_id = f"R{round_number}-{role.value}"
    if status == "failed":
        return Argument(
            argument_id=argument_id, role=role, round=round_number, stance=None, summary="", claims=[],
            conditions=[], uncertainties=[], rebuttal=None, revisions=None, stance_changed=False,
            retrieved_passage_ids=[], repair_used=True, status="failed", failure_reason="Synthetic failure",
        )
    return Argument(
        argument_id=argument_id, role=role, round=round_number, stance=stance,
        summary=f"Synthetic {role.value} summary.", claims=[claim(argument_id, grounded=grounded)],
        conditions=[], uncertainties=[], rebuttal=None, revisions=None, stance_changed=False,
        retrieved_passage_ids=[], repair_used=False, status="ok", failure_reason=None,
    )


def score(argument_id: str, round_number: int) -> Score:
    return Score(
        judge="JUDGE_A", argument_id=argument_id, model="fake/judge", round=round_number,
        groundedness=4, logic=4, uncertainty=4,
        counterarguments=4 if round_number == 2 else None,
        justification={"groundedness": "Supported.", "logic": "Coherent.",
                       "uncertainty": "Clear.", **({"counterarguments": "Answered."} if round_number == 2 else {})},
        untraceable_claims=[], feedback=[],
    )


RED_TEAM = RedTeamReport(
    findings=[RedTeamFinding(
        finding_id="RT-1", category="missing_info", severity="medium",
        description="A synthetic check is missing.", evidence_ids=["CASE-tests"],
        affected_roles=[Role.SURG], suggested_action="Obtain the synthetic check.",
    )],
    injection_check=InjectionCheck(
        scanner_flag_count=0, claims_citing_flagged_lines=[], verdict="no_sign", notes="No flagged lines.",
    ),
)

PRIVACY = PrivacySummary(
    synthetic_marker_found=True, ingest_identifier_hits=0, outbound_prompts_checked=5,
    outbound_prompts_blocked=0, approved_providers=["fake"], providers_used=["fake"],
)


def judge_summary(failed: bool = False) -> JudgeSummary:
    return JudgeSummary(
        mean_score=RoundMeans(round1=4.0, round2=4.0), disagreement_count=0,
        judges=[], failed_judge_calls=[FailedJudgeCall(judge="JUDGE_B", round=2)] if failed else [],
        round_comparison=[], code_ungrounded_claims=[],
    )


def draft_json(*, basis: list[str] | None = None, strongest: list[str] | None = None,
               action_ids: list[str] | None = None, notes: dict[str, str] | None = None,
               narrative: str | None = None) -> str:
    return json.dumps({
        "recommendation": "proceed_with_modifications",
        "recommendation_basis": basis if basis is not None else ["R2-SURG", "R1-PHYS"],
        "strongest_for": strongest if strongest is not None else ["R2-SURG-C1"],
        "strongest_against": [],
        "required_actions": [{"text": "Obtain the synthetic check.",
                              "source_ids": action_ids if action_ids is not None else ["RT-1"]}],
        "role_notes": notes if notes is not None else {
            "SURG": "Supports proceeding.", "PHYS": "Supports proceeding conditionally.",
        },
        "narrative": narrative if narrative is not None else
            "Proceed with modifications based on the final evidence [R2-SURG-C1] [RT-1].",
    })


def make_gateway(config: Config, tmp_path: Path, script: list) -> tuple[LLMGateway, Path, FakeProvider]:
    provider = FakeProvider("fake", script)
    path = tmp_path / "trace.jsonl"
    gateway = LLMGateway(config, Budget(config.budget), TraceWriter(path, "run-chair-synthetic"),
                         {"fake": provider}, sleep_fn=lambda seconds: None)
    return gateway, path, provider


def events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run(config: Config, tmp_path: Path, script: list, *, arguments: list[Argument] | None = None,
        scores: list[Score] | None = None, summary: JudgeSummary | None = None):
    args = arguments if arguments is not None else [
        argument(Role.SURG, 1), argument(Role.SURG, 2), argument(Role.PHYS, 1, stance="conditional"),
    ]
    raw_scores = scores if scores is not None else [score("R1-SURG", 1), score("R2-SURG", 2), score("R1-PHYS", 1)]
    gateway, path, provider = make_gateway(config, tmp_path, script)
    report = chair.run_chair(
        run_id="run-synthetic", case_id="synthetic01", arguments=args, scores=raw_scores,
        red_team=RED_TEAM, privacy_summary=PRIVACY, judge_summary=summary or judge_summary(),
        gateway=gateway, prompts_dir=REAL_PROMPTS,
    )
    return report, path, provider


def test_good_chair_result_uses_final_arguments_and_code_owned_fields(config: Config, tmp_path: Path) -> None:
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=draft_json(), tokens_in=5, tokens_out=5)])

    assert report.status == "COMPLETE"
    assert report.recommendation == "proceed_with_modifications"
    assert report.confidence is not None and report.confidence.inputs.specialists_counted == 2
    assert report.dissent == [] and report.council_warning is None
    assert report.disclaimer == "decision support only, requires human clinical sign-off, synthetic data"
    assert report.red_team_findings == RED_TEAM.findings
    assert report.injection_check == RED_TEAM.injection_check
    assert report.human_decision is None
    prompt = events(path)[0]["prompt"]
    assert "R2-SURG" in prompt and "R1-PHYS" in prompt
    assert '"argument_id": "R1-SURG"' not in prompt
    assert '"argument_id": "R2-SURG"' in prompt
    assert '"confidence":' not in prompt and '"dissent":' not in prompt and '"disclaimer":' not in prompt


def test_invalid_chair_ids_share_one_repair_retry(config: Config, tmp_path: Path) -> None:
    bad = draft_json(basis=["R1-SURG"], strongest=["R1-SURG-C1"], action_ids=["UNKNOWN"])
    report, path, _ = run(config, tmp_path, [
        Scripted(raw_output=bad, tokens_in=5, tokens_out=5),
        Scripted(raw_output=draft_json(), tokens_in=5, tokens_out=5),
    ])
    assert report.recommendation is not None
    trace = events(path)
    assert [event["repair"] for event in trace] == [False, True]
    assert "final-round argument IDs" in trace[1]["prompt"]
    assert "final-round claim IDs" in trace[1]["prompt"]
    assert "UNKNOWN" in trace[1]["prompt"]


def test_nonfinal_recommendation_basis_alone_triggers_repair(config: Config, tmp_path: Path) -> None:
    bad = draft_json(basis=["R1-SURG"])
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "final-round argument IDs" in events(path)[1]["prompt"]


def test_nonfinal_strongest_claim_alone_triggers_repair(config: Config, tmp_path: Path) -> None:
    bad = draft_json(strongest=["R1-SURG-C1"])
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "final-round claim IDs" in events(path)[1]["prompt"]


def test_unknown_action_source_alone_triggers_repair(config: Config, tmp_path: Path) -> None:
    bad = draft_json(action_ids=["UNKNOWN"])
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "UNKNOWN" in events(path)[1]["prompt"]


def test_ungrounded_strongest_claim_triggers_repair(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG, 1, grounded=False)]
    repaired = draft_json(basis=["R1-SURG"], strongest=[], notes={"SURG": "Conditional support."},
                          narrative="Human review remains required [R1-SURG].")
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=draft_json(
        basis=["R1-SURG"], strongest=["R1-SURG-C1"], notes={"SURG": "Support."},
        narrative="Review the claim [R1-SURG-C1].")), Scripted(raw_output=repaired)],
        arguments=args, scores=[score("R1-SURG", 1)])
    assert report.strongest_for == []
    assert "grounded claims only" in events(path)[1]["prompt"]


def test_narrative_requires_real_id_at_end_of_every_sentence(config: Config, tmp_path: Path) -> None:
    bad = draft_json(narrative="First sentence has no tag. Second uses a fake tag [NOPE].")
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    repair = events(path)[1]["prompt"]
    assert "must end with at least one ID tag" in repair and "NOPE" in repair


def test_narrative_unknown_id_alone_triggers_repair(config: Config, tmp_path: Path) -> None:
    bad = draft_json(narrative="The sentence ends in a syntactically valid tag [NOPE].")
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "uses IDs that do not exist: NOPE" in events(path)[1]["prompt"]


def test_narrative_missing_end_tag_alone_triggers_repair(config: Config, tmp_path: Path) -> None:
    bad = draft_json(narrative="The sentence mentions [RT-1] before uncited closing words.")
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "must end with at least one ID tag" in events(path)[1]["prompt"]


def test_role_notes_must_cover_exactly_non_failed_final_specialists(config: Config, tmp_path: Path) -> None:
    bad = draft_json(notes={"SURG": "Only one note.", "ADMIN": "Not present."})
    report, path, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=draft_json())])
    assert report.recommendation is not None
    assert "missing: PHYS" in events(path)[1]["prompt"]
    assert "not a non-failed final specialist: ADMIN" in events(path)[1]["prompt"]


def test_chair_failure_writes_bare_report(config: Config, tmp_path: Path) -> None:
    bad = draft_json(basis=["NOT-REAL"])
    report, _, _ = run(config, tmp_path, [Scripted(raw_output=bad), Scripted(raw_output=bad)])
    assert report.status == "INCOMPLETE" and report.recommendation is None and report.confidence is None
    assert report.recommendation_basis == [] and report.strongest_for == [] and report.required_actions == []
    assert report.role_notes == {} and report.dissent == [] and report.narrative == ""
    assert report.failed_turns == ["CHAIR"]
    assert any(reason.startswith("chair failed:") for reason in report.incomplete_reasons)
    assert report.red_team_findings == RED_TEAM.findings and report.disclaimer


def test_all_specialists_failed_skips_chair_and_writes_bare_report(config: Config, tmp_path: Path) -> None:
    args = [argument(role, 1, status="failed") for role in (Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN)]
    report, _, provider = run(config, tmp_path, [Scripted(raw_output=draft_json())], arguments=args, scores=[])
    assert provider.calls_made == 0
    assert report.recommendation is None and report.status == "INCOMPLETE"
    assert "all specialists failed" in report.incomplete_reasons
    assert report.failed_turns == ["R1-SURG", "R1-PHYS", "R1-ANAES", "R1-ADMIN"]


def test_failed_turns_and_supplied_reasons_make_full_report_incomplete(config: Config, tmp_path: Path) -> None:
    args = [argument(Role.SURG, 1), argument(Role.PHYS, 1, status="failed")]
    gateway, _, _ = make_gateway(config, tmp_path, [Scripted(raw_output=draft_json(
        basis=["R1-SURG"], strongest=["R1-SURG-C1"], notes={"SURG": "Supports proceeding."},
        narrative="Proceed after review [R1-SURG-C1]."))])
    report = chair.run_chair(
        run_id="run-synthetic", case_id="synthetic01", arguments=args, scores=[score("R1-SURG", 1)],
        red_team=RED_TEAM, privacy_summary=PRIVACY, judge_summary=judge_summary(failed=True), gateway=gateway,
        incomplete_reasons=["budget exhausted after Round 1"], prompts_dir=REAL_PROMPTS,
    )
    assert report.status == "INCOMPLETE"
    assert report.failed_turns == ["R1-PHYS", "JUDGE_B"]
    assert report.incomplete_reasons == [
        "R1-PHYS failed: Synthetic failure", "JUDGE_B failed in Round 2", "budget exhausted after Round 1",
    ]


def test_code_computes_dissent_and_majority_warning(config: Config, tmp_path: Path) -> None:
    args = [
        argument(Role.SURG, 1, stance="against"),
        argument(Role.PHYS, 1, stance="against"),
        argument(Role.ANAES, 1, stance="for"),
    ]
    output = draft_json(
        basis=["R1-ANAES"], strongest=["R1-ANAES-C1"], action_ids=["RT-1"],
        notes={"SURG": "Opposes proceeding.", "PHYS": "Opposes proceeding.", "ANAES": "Supports proceeding."},
        narrative="The council records divided positions [R1-ANAES] [R1-SURG] [R1-PHYS].",
    )
    report, _, _ = run(config, tmp_path, [Scripted(raw_output=output)], arguments=args,
                       scores=[score(argument.argument_id, 1) for argument in args])
    assert [item.role for item in report.dissent] == [Role.SURG, Role.PHYS]
    assert [item.note for item in report.dissent] == ["Opposes proceeding.", "Opposes proceeding."]
    assert report.council_warning is not None
