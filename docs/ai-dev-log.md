# AI development log

This file is part of the submission. Keep it honest. The panel scores where AI tools helped, where they failed, and what was checked by hand.

## How the design was made

**Edit this section so it says exactly what happened.**

I used Claude in a chat as a sounding board. It drafted the design documents (`design.md`, `data-contracts.md`) and the architecture diagram, and it reviewed them twice. I chose which suggestions to accept, added several ideas of my own, and can explain every choice. The first review found 8 gaps and a second check found 3 more, all fixed before any code was written.

Codex (OpenAI's coding agent) then built the code from those documents, one task at a time. It did not write the prompts or the rubric anchors. I wrote those.

## Decisions

The last column is the important one. Write your own reasons, in your own words, so you can defend each one.

| Decision | Who proposed it | Why, in my own words |
|---|---|---|
| Hand-written orchestrator, no agent framework | AI draft, I approved | |
| Markdown case format with fixed headings | AI draft, I approved | |
| BM25 keyword retrieval, one KB per role | AI draft, I approved | |
| Judges on a different model from the specialists | Me | |
| Clickable report page | Me | |
| In-process `LLMGateway`, no external service | Me (the idea), AI (the in-process design) | |
| Judges' notes feed Round 2 | Me | |
| Chair budget reserve, dissent table, confidence formula, quote rules | AI (found in review), I approved | |
| Code sets all trust fields, the chair only points to claim IDs | AI draft, I approved | |
| The split: I design and write prompts, the coding agent types the code | Me | |

## Task log

One row per task. Fill it in as you go, not at the end.

| Task | Tool and how it was used | What worked | What went wrong | What I verified by hand |
|---|---|---|---|---|
| T0 | Codex read the instructions and design/contracts/tasks, then created package metadata, the src-layout council package, minimal CLI help, and three CLI tests. | `.venv/Scripts/python.exe -m pytest`: 3 passed. From `src/`, `../.venv/Scripts/python.exe -m council --help` exited 0 and displayed the decision-support, human-sign-off and synthetic-data disclaimer. No model calls. | Initially stopped because setuptools was missing; the human installed it. Pytest passed with a cache-write permission warning in the sandbox. Nothing was downloaded or installed by Codex. | |
| T1 | Codex implemented 62 Pydantic contract/draft/helper models and 16 enums, then performed contract and mutation checks. | 601 tests pass; all 115 final mutations detected; full JSON round trips and nested draft trust boundaries tested. | T1 first stopped on contract gaps; the human resolved them. Mutation review found missing non-finite-number test coverage; tests were added and the mutation repeated successfully. An audit-script targeting error was corrected. See details below. | |
| T2 | Codex added YAML loading and configuration policy validation, with reusable mutation specifications. | 658 tests passed; all 28 T2 mutations detected and restored. | Initial model-error messages were too broad; corrected. Duplicate-key mutation exposed a test gap; added a valid-config regression test and corrected its expected mutation test name. | |

### T0 review notes

- Only the skeleton is implemented. No run command or council behavior is available yet.
- The package uses the planned `src/` layout. Pytest adds `src` to its import path via `pyproject.toml`; the module-help smoke test starts a separate Python process in `src/`.
- To check help without installing anything, run `../.venv/Scripts/python.exe -m council --help` from `src/`. Running from the repository root requires adding `src` to the Python import path or a human-managed editable install. Installation was not performed because AGENTS.md prohibits it.
- The documented runtime dependencies are declared, with pytest as a test extra and setuptools as the build backend. Building/installing the package was not tested.
- No contract uncertainty affected T0. Human verification is still pending; the checks above were performed by Codex.

## Where the tools were not trustworthy

Collect real examples here. Examples of the kind of thing to record: a test that passed but did not test the rule, a citation check that was too loose, a summary that claimed something the code did not do.

-

## What I would tell the next person about using these tools

-

### T1 contract models and audit

Decision support only; requires human clinical sign-off; synthetic data only.

- T1 initially stopped because failed arguments, bare reports and aggregate shapes were unspecified. The human updated the contracts and design, including failed-judge rule 18. Those human-owned changes were committed separately as `ecf89a6` (`Docs: close contract gaps found in T1`). Codex did not edit their content.
- Implementation commit: `ea3a0b8` (`T1: contract models with tests`). Added tests from audit: `4e177d6` (`T1: strengthen numeric and nested draft tests`). No later task was started, no dependencies were installed, and no provider/model calls were made. These serialization tests need no FakeProvider; its implementation remains T8.
- Validation: `.venv/Scripts/python.exe -m pytest -p no:cacheprovider` reports **601 passed**, including after all mutations were restored. The cache plugin was disabled because the sandbox previously denied pytest cache writes. `git diff --check` passed.
- Mutation method: change only `src/council/models.py`, run the entire suite in a fresh Python process, require pytest exit code 1 and the expected failing test, then run `git restore src/council/models.py` and confirm empty `git status --porcelain` before the next mutation. All **115** final mutations were detected. The audit used an unused bytecode-cache path and disabled bytecode writes so small edits could not reuse stale compiled code. Temporary audit scripts/results live only in the ignored `.venv/`; the table below is the committed evidence.
- What went wrong: the first audit script selected the first matching enum assignment globally, so the Round2Status mutation changed TurnStatus instead. Tests failed, the source was restored, and the script was corrected to use each class's source location. That failed audit attempt is not counted as a successful Round2Status check; its corrected rerun is.
- A real coverage gap: changing `allow_inf_nan=False` to `True` initially left all 589 tests green. Added `test_finite_numbers` for NaN and both infinities in unbounded float fields, plus direct Round 2 nested-draft tests; committed them and repeated the mutation. It now fails. The first surviving attempt is not hidden by the final result table.
- The human-verification column is empty. No human spot-check is claimed. The earlier agent-written T0 placeholder in that column was removed; its review instructions remain in the T0 notes.

#### Contract check: fields and implementation

All classes below are in `src/council/models.py`; tests are in `tests/test_models.py`. Each row lists every field touched for that model. `test_contract_round_trip_and_fields[Model]` checks the exact field set, JSON schema property names and JSON round trip; `test_required_fields[Model-field]` checks each required field, and `test_extra_fields_rejected[Model]` rejects unspecified fields. The only defaults are the optional human comment, optional role persona, and fixed disclaimer; dedicated tests cover them. Draft rows contain only LLM-owned fields; nested drafts never use full trust-bearing records.

| Contract section | Implementation class | Fields | Shape/round-trip test |
|---|---|---|---|
| 3 | `InjectionFlag` | `section_id`, `line_number`, `matched_pattern` | `test_contract_round_trip_and_fields[InjectionFlag]` |
| 3 | `CaseSection` | `id`, `heading`, `text`, `flagged`, `flag_reasons` | `test_contract_round_trip_and_fields[CaseSection]` |
| 3 | `CaseContext` | `case_id`, `source_file`, `case_hash`, `title`, `sections`, `missing_sections`, `injection_flags` | `test_contract_round_trip_and_fields[CaseContext]` |
| 4 | `Passage` | `id`, `kb`, `source_title`, `text` | `test_contract_round_trip_and_fields[Passage]` |
| 4 | `RetrievalResult` | `role`, `round`, `query`, `passages`, `scores` | `test_contract_round_trip_and_fields[RetrievalResult]` |
| 5 | `CitationDraft` | `passage_id`, `quote` | `test_contract_round_trip_and_fields[CitationDraft]` |
| 5 | `Citation` | `passage_id`, `quote`, `source_type`, `verified`, `verify_note` | `test_contract_round_trip_and_fields[Citation]` |
| 5 | `ClaimDraft` | `text`, `citations` | `test_contract_round_trip_and_fields[ClaimDraft]` |
| 5 | `Claim` | `claim_id`, `text`, `citations`, `grounding_status` | `test_contract_round_trip_and_fields[Claim]` |
| 5 | `RebuttalDraft` | `target_argument_id`, `target_claim_id`, `why_strongest`, `response_claims` | `test_contract_round_trip_and_fields[RebuttalDraft]` |
| 5 | `Rebuttal` | `target_argument_id`, `target_claim_id`, `why_strongest`, `response_claims` | `test_contract_round_trip_and_fields[Rebuttal]` |
| 5 | `RevisionDraft` | `round1_claim_id`, `action`, `new_claim_index`, `reason` | `test_contract_round_trip_and_fields[RevisionDraft]` |
| 5 | `Revision` | `round1_claim_id`, `action`, `new_claim_index`, `reason`, `new_claim_id` | `test_contract_round_trip_and_fields[Revision]` |
| 5 | `ArgumentDraft` | `stance`, `summary`, `claims`, `conditions`, `uncertainties`, `rebuttal`, `revisions` | `test_contract_round_trip_and_fields[ArgumentDraft]` |
| 5 | `Argument` | `stance`, `summary`, `claims`, `conditions`, `uncertainties`, `rebuttal`, `revisions`, `argument_id`, `role`, `round`, `stance_changed`, `retrieved_passage_ids`, `repair_used`, `status`, `failure_reason` | `test_contract_round_trip_and_fields[Argument]` |
| 6 | `UntraceableClaim` | `claim_id`, `reason` | `test_contract_round_trip_and_fields[UntraceableClaim]` |
| 6 | `FeedbackNote` | `claim_id`, `note` | `test_contract_round_trip_and_fields[FeedbackNote]` |
| 6 | `ScoreDraft` | `groundedness`, `logic`, `uncertainty`, `counterarguments`, `justification`, `untraceable_claims`, `feedback` | `test_contract_round_trip_and_fields[ScoreDraft]` |
| 6 | `Score` | `groundedness`, `logic`, `uncertainty`, `counterarguments`, `justification`, `untraceable_claims`, `feedback`, `judge`, `argument_id`, `model`, `round` | `test_contract_round_trip_and_fields[Score]` |
| 6 | `FailedJudgeCall` | `judge`, `round` | `test_contract_round_trip_and_fields[FailedJudgeCall]` |
| 6 | `CriterionMeans` | `groundedness`, `logic`, `uncertainty`, `counterarguments` | `test_contract_round_trip_and_fields[CriterionMeans]` |
| 6 | `CriterionGaps` | `groundedness`, `logic`, `uncertainty`, `counterarguments` | `test_contract_round_trip_and_fields[CriterionGaps]` |
| 6 | `ArgumentScoreSummary` | `argument_id`, `role`, `round`, `judges_scored`, `mean`, `gap`, `disagreement_count` | `test_contract_round_trip_and_fields[ArgumentScoreSummary]` |
| 6 | `RoundMeans` | `round1`, `round2` | `test_contract_round_trip_and_fields[RoundMeans]` |
| 6 | `SharedScore` | `round1`, `round2`, `change` | `test_contract_round_trip_and_fields[SharedScore]` |
| 6 | `UngroundedCounts` | `round1`, `round2` | `test_contract_round_trip_and_fields[UngroundedCounts]` |
| 6 | `RevisionCounts` | `kept`, `revised`, `dropped` | `test_contract_round_trip_and_fields[RevisionCounts]` |
| 6 | `RoundComparison` | `role`, `shared_score`, `ungrounded_claims`, `revisions`, `round2_status` | `test_contract_round_trip_and_fields[RoundComparison]` |
| 6 | `Scorecard` | `run_id`, `scores`, `presented_order`, `skipped_arguments`, `failed_judge_calls`, `per_argument`, `code_ungrounded_claims`, `round_comparison` | `test_contract_round_trip_and_fields[Scorecard]` |
| 7 | `RedTeamFindingDraft` | `category`, `severity`, `description`, `evidence_ids`, `affected_roles`, `suggested_action` | `test_contract_round_trip_and_fields[RedTeamFindingDraft]` |
| 7 | `RedTeamFinding` | `category`, `severity`, `description`, `evidence_ids`, `affected_roles`, `suggested_action`, `finding_id` | `test_contract_round_trip_and_fields[RedTeamFinding]` |
| 7 | `InjectionCheckDraft` | `verdict`, `notes` | `test_contract_round_trip_and_fields[InjectionCheckDraft]` |
| 7 | `InjectionCheck` | `verdict`, `notes`, `scanner_flag_count`, `claims_citing_flagged_lines` | `test_contract_round_trip_and_fields[InjectionCheck]` |
| 7 | `RedTeamReportDraft` | `findings`, `injection_check` | `test_contract_round_trip_and_fields[RedTeamReportDraft]` |
| 7 | `RedTeamReport` | `findings`, `injection_check` | `test_contract_round_trip_and_fields[RedTeamReport]` |
| 8, 12 | `Penalty` | `count`, `penalty` | `test_contract_round_trip_and_fields[Penalty]` |
| 8, 12 | `ConfidenceInputs` | `judge_part`, `judge_round_used`, `agreement_part`, `specialists_counted`, `specialists_accepting`, `base`, `ungrounded_claims`, `high_severity_findings`, `judge_disagreements`, `total_penalty` | `test_contract_round_trip_and_fields[ConfidenceInputs]` |
| 8, 12 | `Confidence` | `level`, `score`, `inputs` | `test_contract_round_trip_and_fields[Confidence]` |
| 8, 12 | `JudgeParticipation` | `judge`, `model`, `rounds_scored` | `test_contract_round_trip_and_fields[JudgeParticipation]` |
| 8, 12 | `JudgeSummary` | `mean_score`, `disagreement_count`, `judges`, `failed_judge_calls`, `round_comparison`, `code_ungrounded_claims` | `test_contract_round_trip_and_fields[JudgeSummary]` |
| 8, 12 | `RequiredAction` | `text`, `source_ids` | `test_contract_round_trip_and_fields[RequiredAction]` |
| 8, 12 | `Dissent` | `role`, `stance`, `argument_id`, `note` | `test_contract_round_trip_and_fields[Dissent]` |
| 8, 12 | `ReportDraft` | `recommendation`, `recommendation_basis`, `strongest_for`, `strongest_against`, `required_actions`, `role_notes`, `narrative` | `test_contract_round_trip_and_fields[ReportDraft]` |
| 8, 12 | `Report` | `recommendation`, `recommendation_basis`, `strongest_for`, `strongest_against`, `required_actions`, `role_notes`, `narrative`, `run_id`, `case_id`, `status`, `incomplete_reasons`, `failed_turns`, `confidence`, `council_warning`, `dissent`, `red_team_findings`, `injection_check`, `judge_summary`, `citations_index`, `disclaimer`, `human_decision` | `test_contract_round_trip_and_fields[Report]` |
| 9 | `HumanDecision` | `run_id`, `decision`, `comment`, `reviewer`, `decided_at`, `report_hash` | `test_contract_round_trip_and_fields[HumanDecision]` |
| 10 | `TraceEvent` | `run_id`, `seq`, `timestamp`, `step`, `event_type`, `role`, `round`, `model`, `prompt`, `retrieved_passage_ids`, `raw_output`, `parsed_ref`, `tokens_in`, `tokens_out`, `latency_ms`, `attempt`, `repair`, `budget_tokens_used`, `error` | `test_contract_round_trip_and_fields[TraceEvent]` |
| 11 / config.yaml | `BudgetState` | `tokens_used`, `calls_used`, `started_at`, `exhausted`, `reason` | `test_contract_round_trip_and_fields[BudgetState]` |
| 11 / config.yaml | `ModelChoice` | `provider`, `model` | `test_contract_round_trip_and_fields[ModelChoice]` |
| 11 / config.yaml | `ModelChoices` | `specialist`, `chair`, `red_team`, `judge_a`, `judge_b` | `test_contract_round_trip_and_fields[ModelChoices]` |
| 11 / config.yaml | `RoleValues` | `specialist`, `judge`, `red_team`, `chair` | `test_contract_round_trip_and_fields[RoleValues]` |
| 11 / config.yaml | `TokenCaps` | `specialist`, `judge`, `red_team`, `chair` | `test_contract_round_trip_and_fields[TokenCaps]` |
| 11 / config.yaml | `ChairReserve` | `tokens`, `seconds`, `calls` | `test_contract_round_trip_and_fields[ChairReserve]` |
| 11 / config.yaml | `BudgetConfig` | `max_total_tokens`, `max_calls`, `max_seconds_total`, `chair_reserve`, `max_tokens_per_call` | `test_contract_round_trip_and_fields[BudgetConfig]` |
| 11 / config.yaml | `RetryConfig` | `max_repair_retries_per_turn`, `max_api_attempts`, `api_retry_wait_seconds` | `test_contract_round_trip_and_fields[RetryConfig]` |
| 11 / config.yaml | `RetrievalConfig` | `top_k`, `case_sections` | `test_contract_round_trip_and_fields[RetrievalConfig]` |
| 11 / config.yaml | `GroundingConfig` | `quote_words_min`, `quote_words_max` | `test_contract_round_trip_and_fields[GroundingConfig]` |
| 11 / config.yaml | `JudgingConfig` | `disagreement_gap`, `feedback_max_notes`, `feedback_max_words` | `test_contract_round_trip_and_fields[JudgingConfig]` |
| 11 / config.yaml | `PathsConfig` | `cases`, `runs`, `prompts` | `test_contract_round_trip_and_fields[PathsConfig]` |
| 11 / config.yaml | `RoleConfig` | `name`, `kb`, `keywords`, `persona_prompt` | `test_contract_round_trip_and_fields[RoleConfig]` |
| 11 / config.yaml | `Config` | `paths`, `models`, `temperature`, `budget`, `retries`, `retrieval`, `grounding`, `judging`, `roles` | `test_contract_round_trip_and_fields[Config]` |
| 14 | `Source` | `source_type`, `source_title`, `text` | `test_contract_round_trip_and_fields[Source]` |
| 14 | `RunBundle` | `run_id`, `case_id`, `created_at`, `config_snapshot`, `case_context`, `retrievals`, `arguments`, `scorecard`, `red_team`, `report`, `sources` | `test_contract_round_trip_and_fields[RunBundle]` |


#### Contract check: rules and scope

No new aggregate wire shapes were invented. Named helper classes implement exactly the nested field sets in the updated contracts. The configuration models follow the existing human-owned `config.yaml` layout; configuration loading and policy validation remain T2. `config_snapshot` remains the specified JSON object, not a new invented configuration shape.

| Rule/contract | T1 implementation | Tests / work intentionally assigned to later tasks |
|---|---|---|
| Section 1 role codes and all enumerated values in sections 5–10 | `Role`, `Stance`, `SourceType`, `GroundingStatus`, `RevisionAction`, `TurnStatus`, `Round2Status`, `Criterion`, `FindingCategory`, `Level`, `InjectionVerdict`, `ReportStatus`, `Recommendation`, `Decision`, `Step`, `EventType`; `Judge` and `Round` aliases | `test_enum_values`, `test_every_enum_is_checked`, `test_judges_only`, `test_two_rounds_and_attempts_only`. IDs remain strings as specified; creation, prefix/existence and cross-record checks belong to later ingest/grounding/agent tasks. |
| Section 2 case headings and section 3 exact case text | `CaseSection`, `CaseContext`, `InjectionFlag` preserve fields and text | Shape tests and `test_source_and_trace_text_is_preserved`; heading-to-ID mapping, hashing and scanner behavior remain T3. |
| Section 4 passages/retrieval | `Passage`, `RetrievalResult` | Shape tests; loading, BM25, top-k and query construction remain T4. |
| Rule 1 parse contracts | All Pydantic models; `ContractModel` rejects extra fields and non-finite floats | Shape, required/extra-field, rating and finite-number tests. API/repair retries and failed-turn orchestration remain T8–T15. |
| Rules 2–4 citation/grounding | `CitationDraft`, `Citation`, `ClaimDraft`, `Claim` | `test_missing_evidence_can_be_preserved` accepts missing citations, unknown IDs and bad quotes so T5 can repair/mark them ungrounded; quote/source verification is deliberately not performed by schema validation. |
| Rule 5 rebuttal targets | `RebuttalDraft`, `Rebuttal`; `Argument.check_failure` prohibits Round 1 rebuttals/revisions | Round-trip, nested draft and `test_round1_has_no_rebuttal_or_revisions` tests; target existence, role and membership checks remain T12. |
| Section 6 score bounds and round-only fields | `Rating`, `Score.check_round` | `test_rating_bounds_and_integer_type`, `test_all_rating_values`, `test_score_round_rules`, `test_round2_score_round_trip`. |
| Rule 6 judge coverage/order | `Score`, `Scorecard.presented_order`, `skipped_arguments`, summaries | Shape tests; batching, shuffled order and once-per-argument coverage remain T11. |
| Rule 7 red-team evidence | Red-team draft/full models and typed evidence-ID lists | Shape/nested-draft tests; evidence existence remains T13. |
| Rule 8 chair IDs and strongest claims | `ReportDraft`, `Report`, `RequiredAction`; lists remain IDs, not invented copied-text fields | Shape tests; ID checks, final-round selection and text lookup remain T14/T19. |
| Rule 9 code-owned trust fields | Draft/full separation; `ContractModel` extra-field rejection; fixed `Report.disclaimer` | `test_drafts_reject_code_owned_fields`, `test_draft_schemas_do_not_expose_code_fields`, `test_nested_drafts_reject_trust_fields`, `test_round2_draft_rejects_nested_full_records`, `test_fixed_disclaimer`. Dissent/confidence calculation remains T6/T14. |
| Section 8 bare report / rule 10 bare fallback shape | `Report.check_bare_report`: INCOMPLETE; null recommendation/confidence/warning; empty chair fields and dissent | `test_bare_report_round_trip`, `test_bare_report_rejects_chair_content`, `test_non_bare_report_requires_confidence`; producing a fallback at runtime remains T14/T15. |
| Sections 8 and 12 confidence inputs | `Confidence`, `ConfidenceInputs`, `Penalty`, bounded percentage fields | Shape tests, `test_percentage_bounds`, `test_percentage_endpoints`, `test_no_judge_or_red_team_data_round_trip`. Formula, level thresholds, penalty caps and missing-score calculation remain T6. |
| Section 9 human decision | `HumanDecision`; optional comment defaults to empty string | Shape tests and `test_optional_human_comment_and_red_persona`; user interaction and hashing remain T16. |
| Sections 10–11 / rule 10 budgets and attempts | `TraceEvent`, `BudgetState`, configuration shapes; rounds/attempts limited to 1 or 2 | Shape tests and `test_two_rounds_and_attempts_only`. Budget enforcement, chair reserve and elapsed time remain T7/T8. `BudgetState` is a serializable snapshot, not yet a mutable synchronized budget service. |
| Rule 11 plain-text rendering | Case, source and trace fields retain text unchanged | `test_source_and_trace_text_is_preserved`; HTML escaping/rendering remains T19. |
| Rule 12 counter/trace locks | No shared counters or sequence allocator implemented in T1 | Locking and concurrent tests remain T7; no claim that Pydantic records themselves enforce synchronization. |
| Rule 13 revisions | `RevisionDraft.check_index` enforces positive one-based indices for kept/revised and null for dropped; `Revision` adds code-owned new ID | `test_revision_index_rules`, `test_valid_revision_actions`; full Round 1 coverage, target index range, ID derivation and at-least-one-claim checks remain T12. |
| Rule 14 feedback | `FeedbackNote`, `UntraceableClaim`, `ScoreDraft` preserve feedback, including oversized input for later truncation | `test_missing_evidence_can_be_preserved`; truncation and passing only feedback/untraceable claims/code checks remain T9/T11/T12. |
| Rule 15 no prior scores shown to Round 2 judges | Score models record their own round | `test_round2_score_round_trip`; prompt assembly/input selection remains T11. |
| Rule 16 failed Round 1 skips Round 2 | `Round2Status.SKIPPED`, `RoundComparison` and failed `Argument` shape | Enum and round-trip tests; actual skip/fallback flow remains T12/T15. |
| Rule 17 failed argument | `Argument.check_failure` enforces null stance iff failed, empty lists, null rebuttal/revisions, failure reason; successful argument requires a stance and null reason | `test_failed_argument_round_trip`, `test_failed_argument_rejects_content`, `test_ok_argument_requires_stance_and_no_failure`. |
| Rule 18 failed judge | `FailedJudgeCall`, `Scorecard.failed_judge_calls`, `JudgeSummary.failed_judge_calls`, nullable per-criterion gaps/round means and `judge_round_used` | Shape tests include a single-judge summary with null per-criterion gaps and zero disagreements; `test_no_judge_or_red_team_data_round_trip` preserves missing scores. Mean/gap calculation, continuing the run and setting INCOMPLETE remain T6/T11/T14/T15. |
| Section 14 run bundle | `RunBundle` and `Source` use the exact supplied field sets and nullable red team | Round-trip tests and missing-red-team case. Populating all referenced sources, writing files and constructing a secret-free snapshot remain T15/T16; arbitrary JSON snapshot content is not inspected for secrets by this schema. |

No T1 shape deviations remain after the human's clarifications. Deferred runtime rules above are not represented as completed behavior. T1 does not compute confidence, derive trust, verify citation meaning, enforce budget locks, or execute any council turn.

#### Mutation table

Each row is a separately tested mutation of committed `src/council/models.py`. All rows below produced at least one failing test and were undone with `git restore`, followed by a clean status check. Test names refer to `tests/test_models.py`; parameterized failures are grouped by test function for readability. Shape rows each remove one field from that class. This is a finite mutation audit, not a claim of exhaustive mutation coverage.

| # | Rule | What was broken | Test that failed |
|---|---|---|---|
| 1 | Exact enum Role | `SURG = "SURG" -> INVALID = "INVALID"` | `test_enum_values` |
| 2 | Exact enum Stance | `FOR = "for" -> FOR = "INVALID"` | `test_enum_values` |
| 3 | Exact enum SourceType | `CASE = "case" -> CASE = "INVALID"` | `test_enum_values` |
| 4 | Exact enum GroundingStatus | `GROUNDED = "grounded" -> GROUNDED = "INVALID"` | `test_enum_values` |
| 5 | Exact enum RevisionAction | `KEPT = "kept" -> KEPT = "INVALID"` | `test_enum_values` |
| 6 | Exact enum TurnStatus | `OK = "ok" -> OK = "INVALID"` | `test_enum_values` |
| 7 | Exact enum Round2Status | `Round2Status: OK = "ok" -> OK = "INVALID"` | `test_enum_values` |
| 8 | Exact enum Criterion | `Criterion: GROUNDEDNESS = "groundedness" -> GROUNDEDNESS = "INVALID"` | `test_enum_values` |
| 9 | Exact enum FindingCategory | `FindingCategory: MISSING_INFO = "missing_info" -> MISSING_INFO = "INVALID"` | `test_enum_values` |
| 10 | Exact enum Level | `Level: LOW = "low" -> LOW = "INVALID"` | `test_enum_values` |
| 11 | Exact enum InjectionVerdict | `InjectionVerdict: NO_SIGN = "no_sign" -> NO_SIGN = "INVALID"` | `test_enum_values` |
| 12 | Exact enum ReportStatus | `ReportStatus: COMPLETE = "COMPLETE" -> INVALID = "INVALID"` | `test_enum_values` |
| 13 | Exact enum Recommendation | `Recommendation: PROCEED = "proceed" -> PROCEED = "INVALID"` | `test_enum_values` |
| 14 | Exact enum Decision | `Decision: APPROVED = "approved" -> APPROVED = "INVALID"` | `test_enum_values` |
| 15 | Exact enum Step | `Step: INGEST = "ingest" -> INGEST = "INVALID"` | `test_enum_values` |
| 16 | Exact enum EventType | `EventType: START = "start" -> START = "INVALID"` | `test_enum_values` |
| 17 | Shape InjectionFlag | `InjectionFlag.section_id -> removed field` | `test_contract_round_trip_and_fields` |
| 18 | Shape CaseSection | `CaseSection.id -> removed field` | `test_contract_round_trip_and_fields` |
| 19 | Shape CaseContext | `CaseContext.case_id -> removed field` | `test_contract_round_trip_and_fields` |
| 20 | Shape Passage | `Passage.id -> removed field` | `test_contract_round_trip_and_fields` |
| 21 | Shape RetrievalResult | `RetrievalResult.role -> removed field` | `test_contract_round_trip_and_fields` |
| 22 | Shape CitationDraft | `CitationDraft.passage_id -> removed field` | `test_contract_round_trip_and_fields` |
| 23 | Shape Citation | `Citation.source_type -> removed field` | `test_contract_round_trip_and_fields` |
| 24 | Shape ClaimDraft | `ClaimDraft.text -> removed field` | `test_contract_round_trip_and_fields` |
| 25 | Shape Claim | `Claim.claim_id -> removed field` | `test_contract_round_trip_and_fields` |
| 26 | Shape RebuttalDraft | `RebuttalDraft.target_argument_id -> removed field` | `test_contract_round_trip_and_fields` |
| 27 | Shape Rebuttal | `Rebuttal.target_argument_id -> removed field` | `test_contract_round_trip_and_fields` |
| 28 | Shape RevisionDraft | `RevisionDraft.round1_claim_id -> removed field` | `test_contract_round_trip_and_fields` |
| 29 | Shape Revision | `Revision.new_claim_id -> removed field` | `test_contract_round_trip_and_fields` |
| 30 | Shape ArgumentDraft | `ArgumentDraft.stance -> removed field` | `test_contract_round_trip_and_fields` |
| 31 | Shape Argument | `Argument.argument_id -> removed field` | `test_contract_round_trip_and_fields` |
| 32 | Shape UntraceableClaim | `UntraceableClaim.claim_id -> removed field` | `test_contract_round_trip_and_fields` |
| 33 | Shape FeedbackNote | `FeedbackNote.claim_id -> removed field` | `test_contract_round_trip_and_fields` |
| 34 | Shape ScoreDraft | `ScoreDraft.groundedness -> removed field` | `test_contract_round_trip_and_fields` |
| 35 | Shape Score | `Score.judge -> removed field` | `test_contract_round_trip_and_fields` |
| 36 | Shape FailedJudgeCall | `FailedJudgeCall.judge -> removed field` | `test_contract_round_trip_and_fields` |
| 37 | Shape CriterionMeans | `CriterionMeans.groundedness -> removed field` | `test_contract_round_trip_and_fields` |
| 38 | Shape CriterionGaps | `CriterionGaps.groundedness -> removed field` | `test_contract_round_trip_and_fields` |
| 39 | Shape ArgumentScoreSummary | `ArgumentScoreSummary.argument_id -> removed field` | `test_contract_round_trip_and_fields` |
| 40 | Shape RoundMeans | `RoundMeans.round1 -> removed field` | `test_contract_round_trip_and_fields` |
| 41 | Shape SharedScore | `SharedScore.change -> removed field` | `test_contract_round_trip_and_fields` |
| 42 | Shape UngroundedCounts | `UngroundedCounts.round1 -> removed field` | `test_contract_round_trip_and_fields` |
| 43 | Shape RevisionCounts | `RevisionCounts.kept -> removed field` | `test_contract_round_trip_and_fields` |
| 44 | Shape RoundComparison | `RoundComparison.role -> removed field` | `test_contract_round_trip_and_fields` |
| 45 | Shape Scorecard | `Scorecard.run_id -> removed field` | `test_contract_round_trip_and_fields` |
| 46 | Shape RedTeamFindingDraft | `RedTeamFindingDraft.category -> removed field` | `test_contract_round_trip_and_fields` |
| 47 | Shape RedTeamFinding | `RedTeamFinding.finding_id -> removed field` | `test_contract_round_trip_and_fields` |
| 48 | Shape InjectionCheckDraft | `InjectionCheckDraft.verdict -> removed field` | `test_contract_round_trip_and_fields` |
| 49 | Shape InjectionCheck | `InjectionCheck.scanner_flag_count -> removed field` | `test_contract_round_trip_and_fields` |
| 50 | Shape RedTeamReportDraft | `RedTeamReportDraft.findings -> removed field` | `test_contract_round_trip_and_fields` |
| 51 | Shape RedTeamReport | `RedTeamReport.findings -> removed field` | `test_contract_round_trip_and_fields` |
| 52 | Shape Penalty | `Penalty.count -> removed field` | `test_contract_round_trip_and_fields` |
| 53 | Shape ConfidenceInputs | `ConfidenceInputs.judge_part -> removed field` | `test_contract_round_trip_and_fields` |
| 54 | Shape Confidence | `Confidence.level -> removed field` | `test_contract_round_trip_and_fields` |
| 55 | Shape JudgeParticipation | `JudgeParticipation.judge -> removed field` | `test_contract_round_trip_and_fields` |
| 56 | Shape JudgeSummary | `JudgeSummary.mean_score -> removed field` | `test_contract_round_trip_and_fields` |
| 57 | Shape RequiredAction | `RequiredAction.text -> removed field` | `test_contract_round_trip_and_fields` |
| 58 | Shape Dissent | `Dissent.role -> removed field` | `test_contract_round_trip_and_fields` |
| 59 | Shape HumanDecision | `HumanDecision.run_id -> removed field` | `test_contract_round_trip_and_fields` |
| 60 | Shape ReportDraft | `ReportDraft.recommendation -> removed field` | `test_contract_round_trip_and_fields` |
| 61 | Shape Report | `Report.run_id -> removed field` | `test_contract_round_trip_and_fields` |
| 62 | Shape TraceEvent | `TraceEvent.run_id -> removed field` | `test_contract_round_trip_and_fields` |
| 63 | Shape BudgetState | `BudgetState.tokens_used -> removed field` | `test_contract_round_trip_and_fields` |
| 64 | Shape ModelChoice | `ModelChoice.provider -> removed field` | `test_contract_round_trip_and_fields` |
| 65 | Shape ModelChoices | `ModelChoices.specialist -> removed field` | `test_contract_round_trip_and_fields` |
| 66 | Shape RoleValues | `RoleValues.specialist -> removed field` | `test_contract_round_trip_and_fields` |
| 67 | Shape TokenCaps | `TokenCaps.specialist -> removed field` | `test_contract_round_trip_and_fields` |
| 68 | Shape ChairReserve | `ChairReserve.tokens -> removed field` | `test_contract_round_trip_and_fields` |
| 69 | Shape BudgetConfig | `BudgetConfig.max_total_tokens -> removed field` | `test_contract_round_trip_and_fields` |
| 70 | Shape RetryConfig | `RetryConfig.max_repair_retries_per_turn -> removed field` | `test_contract_round_trip_and_fields` |
| 71 | Shape RetrievalConfig | `RetrievalConfig.top_k -> removed field` | `test_contract_round_trip_and_fields` |
| 72 | Shape GroundingConfig | `GroundingConfig.quote_words_min -> removed field` | `test_contract_round_trip_and_fields` |
| 73 | Shape JudgingConfig | `JudgingConfig.disagreement_gap -> removed field` | `test_contract_round_trip_and_fields` |
| 74 | Shape PathsConfig | `PathsConfig.cases -> removed field` | `test_contract_round_trip_and_fields` |
| 75 | Shape RoleConfig | `RoleConfig.name -> removed field` | `test_contract_round_trip_and_fields` |
| 76 | Shape Config | `Config.paths -> removed field` | `test_contract_round_trip_and_fields` |
| 77 | Shape Source | `Source.source_type -> removed field` | `test_contract_round_trip_and_fields` |
| 78 | Shape RunBundle | `RunBundle.run_id -> removed field` | `test_contract_round_trip_and_fields` |
| 79 | Reject extra/trust fields | `extra="forbid" -> extra="ignore"` | `test_extra_fields_rejected` |
| 80 | Finite numeric values | `allow_inf_nan=False -> allow_inf_nan=True` | `test_finite_numbers` |
| 81 | Rating lower bound | `strict=True, ge=1, le=5 -> strict=True, ge=0, le=5` | `test_rating_bounds_and_integer_type` |
| 82 | Rating upper bound | `strict=True, ge=1, le=5 -> strict=True, ge=1, le=6` | `test_rating_bounds_and_integer_type` |
| 83 | Rating integer type | `strict=True, ge=1, le=5 -> strict=False, ge=1, le=5` | `test_rating_bounds_and_integer_type` |
| 84 | Percentage lower bound | `Field(ge=0, le=100) -> Field(ge=-1, le=100)` | `test_percentage_bounds` |
| 85 | Percentage upper bound | `Field(ge=0, le=100) -> Field(ge=0, le=101)` | `test_percentage_bounds` |
| 86 | Positive revision index | `Field(strict=True, ge=1) -> Field(strict=True, ge=0)` | `test_revision_index_rules` |
| 87 | Round domain | `Round = Literal[1, 2] -> Round = Literal[1, 2, 3]` | `test_two_rounds_and_attempts_only` |
| 88 | Judge domain | `Judge = Literal["JUDGE_A", "JUDGE_B"] -> Judge = Literal["JUDGE_A", "JUDGE_B", "SURG"]` | `test_judges_only` |
| 89 | Attempt domain | `attempt: Literal[1, 2] -> attempt: Literal[1, 2, 3]` | `test_two_rounds_and_attempts_only` |
| 90 | Revision action/index relationship | `if (self.action == RevisionAction.DROPPED) != (self.new_claim_index is None): -> if False:` | `test_revision_index_rules` |
| 91 | Failed stance null | `if self.stance is not None: -> if False:` | `test_failed_argument_rejects_content` |
| 92 | Failed lists empty | `if self.claims or self.conditions or self.uncertainties: -> if False:` | `test_failed_argument_rejects_content` |
| 93 | Failed rebuttal/revisions null | `if self.rebuttal is not None or self.revisions is not None: -> if False:` | `test_failed_argument_rejects_content` |
| 94 | Failed reason required | `if not self.failure_reason: -> if False:` | `test_failed_argument_rejects_content` |
| 95 | Successful stance required | `if self.stance is None: -> if False:` | `test_ok_argument_requires_stance_and_no_failure` |
| 96 | Successful failure reason null | `if self.failure_reason is not None: -> if False:` | `test_ok_argument_requires_stance_and_no_failure` |
| 97 | Round 1 no revision/rebuttal | `if self.round == 1 and (self.rebuttal is not None or self.revisions is not None): -> if False:` | `test_round1_has_no_rebuttal_or_revisions` |
| 98 | Round 1 no counterargument score | `if self.round == 1 and self.counterarguments is not None: -> if False:` | `test_score_round_rules` |
| 99 | Round 2 counterargument score required | `if self.round == 2 and self.counterarguments is None: -> if False:` | `test_score_round_rules` |
| 100 | Round 2 feedback empty | `if self.round == 2 and self.feedback: -> if False:` | `test_score_round_rules` |
| 101 | Bare report incomplete | `if self.status != ReportStatus.INCOMPLETE: -> if False:` | `test_bare_report_rejects_chair_content` |
| 102 | Bare report null confidence/warning | `if self.confidence is not None or self.council_warning is not None: -> if False:` | `test_bare_report_rejects_chair_content` |
| 103 | Bare report empty chair content | `if (self.recommendation_basis or self.strongest_for or self.strongest_against or self.required_actions or self.dissent or self.role_notes or self.narrative): -> if False:` | `test_bare_report_rejects_chair_content` |
| 104 | Non-bare confidence required | `elif self.confidence is None: -> elif False:` | `test_non_bare_report_requires_confidence` |
| 105 | Fixed disclaimer | `disclaimer: Literal[ "decision support only, requires human clinical sign-off, synthetic data" ] = DISCLAIMER -> disclaimer: str = DISCLAIMER` | `test_fixed_disclaimer` |
| 106 | Required fields | `passage_id: str -> passage_id: str = ""` | `test_required_fields` |
| 107 | Optional human comment | `comment: str = "" -> comment: str` | `test_optional_human_comment_and_red_persona` |
| 108 | Optional red-team persona | `persona_prompt: str \| None = None -> persona_prompt: str \| None` | `test_optional_human_comment_and_red_persona` |
| 109 | Nested draft citations: list[CitationDraft] | `citations: list[CitationDraft] -> citations: list[Citation]` | `test_contract_round_trip_and_fields` |
| 110 | Nested draft claims: list[ClaimDraft] | `claims: list[ClaimDraft] -> claims: list[Claim]` | `test_contract_round_trip_and_fields` |
| 111 | Nested draft response_claims: list[ClaimDraft] | `response_claims: list[ClaimDraft] -> response_claims: list[Claim]` | `test_contract_round_trip_and_fields` |
| 112 | Nested draft rebuttal: RebuttalDraft \| None | `rebuttal: RebuttalDraft \| None -> rebuttal: Rebuttal \| None` | `test_round2_argument_draft_round_trip` |
| 113 | Nested draft revisions: list[RevisionDraft] \| None | `revisions: list[RevisionDraft] \| None -> revisions: list[Revision] \| None` | `test_round2_argument_draft_round_trip` |
| 114 | Nested draft findings: list[RedTeamFindingDraft] | `findings: list[RedTeamFindingDraft] -> findings: list[RedTeamFinding]` | `test_contract_round_trip_and_fields` |
| 115 | Nested draft injection_check: InjectionCheckDraft | `injection_check: InjectionCheckDraft -> injection_check: InjectionCheck` | `test_contract_round_trip_and_fields` |


#### Human review starting points

1. `src/council/models.py` — `Argument.check_failure`: the human-resolved failed-turn contract.
2. `src/council/models.py` — `Report.check_bare_report`: the human-resolved bare-report contract.
3. `tests/test_models.py` — `test_drafts_reject_code_owned_fields`: attempts to inject code-owned fields into each draft.

For a short manual mutation spot-check, change the rating lower bound from `ge=1` to `ge=0` and run the suite; `test_rating_bounds_and_integer_type` must fail. Restore `src/council/models.py` afterwards, and fill in the human-verification column yourself.

### Mutation-tool cleanup (before T2)

- Promoted `.venv/t1_mutation_check.py` to tracked `tools/mutation_check.py`; removed the old copy and deleted `.venv/t1_write_log.py` as requested.
- Re-run the complete T1 audit from the repository root with `.venv/Scripts/python.exe tools/mutation_check.py`. Add `--list` to preview, or `--start 79 --end 80` to run just the non-finite-number check. The working tree must be committed and clean.
- Later tasks can reuse the runner with `--target src/council/<file>.py --spec tools/<task>_mutations.json`. Each JSON entry has `rule`, `old`, `new`, and `test` strings; the old text must match exactly once. Results are written to ignored `.venv/mutation-results.json` for the current invocation. A baseline test failure stops the audit before mutation; every mutation is restored with `git restore` even on timeout.
- Tests: 609 passed. The sandbox blocked pytest's temporary-directory setup; rerunning with filesystem approval passed. A PowerShell quoting error in the promotion command was corrected before any source file was generated. Contract impact: none; this is developer tooling, not council behavior.

| Cleanup rule | Mutation | Failing test |
|---|---|---|
| Exact target match | Disabled unique-match check | `test_spec_requires_one_exact_match` |
| Clean/readable tree | Disabled status check | `test_dirty_or_unreadable_tree_refused` |
| Real test failures required | Accepted pytest collection errors | `test_restore_after_every_outcome` |
| Always restore | Replaced restore with status | `test_restore_after_every_outcome` |

All four mutations were detected on committed code and restored with clean status between checks. Re-run with `.venv/Scripts/python.exe tools/mutation_check.py --target tools/mutation_check.py --spec tools/cleanup_mutations.json`. No human verification is claimed.


### T2 configuration and audit

Decision support only; requires human clinical sign-off; synthetic data only.

- Added `src/council/config.py`: safe YAML reading, duplicate-key rejection, strict validation against T1's existing Config model, field-specific ConfigError messages, and the code constant `MAX_ROUNDS = 2`. No new contract shapes were added and the T1 models were not changed.
- Implementation commit: `5ca88b6`. Additional duplicate-key test: `fe0d3ad`; corrected mutation test reference: `cb191b9`. Tool cleanup was committed first as `427f9e0` and `9737143`.
- Tests: `.venv/Scripts/python.exe -m pytest -p no:cacheprovider` reports **658 passed**, including after restoring all mutations. Filesystem approval was needed for pytest's temporary directory; no package installation, network access, credentials, or provider calls were used. `git diff --check` passed.
- What went wrong: two initial tests expected the exact model field name, but relationship errors named only the parent object. Messages now name `models.chair.model`/`provider` or `models.judge_b.model`/`provider`. An instance-level Pydantic metadata access in a test was also corrected to avoid a deprecation warning.
- Mutation review found a real gap: the original duplicate-key input was otherwise invalid, so removing duplicate detection still raised an unrelated configuration error. `test_duplicate_key_in_valid_config` now duplicates a key in an otherwise valid file and requires the duplicate-specific error. Its first audit rerun still referenced the old test; the runner refused to count that unexpected failure, so the JSON specification was corrected and the full audit repeated. All 28 final checks detected their mutations.
- `config.yaml` still has the human's `TBD` model/provider placeholders. Loading it deliberately raises a clear error naming the setting to fill. Tests use synthetic model names; no real providers were chosen. The only change to config.yaml is a comment documenting this behavior.
- Budget totals, positive output caps/reserves, temperatures and retry wait can be tuned within validation bounds. The current contract's explicit retry counts, top-five retrieval, quote boundaries and judge limits/gap are enforced at their specified values. Provider-specific temperature limits belong with later adapters; T2 rejects negative/non-finite temperatures without inventing a provider-specific upper bound.
- Resource paths and text are preserved; prompts/KB files are not opened or required to exist yet. No runtime budget accounting, retrieval, model calls, or T3 work was implemented. The human-verification column remains empty.

Re-run T2's complete mutation audit from the repository root:

```powershell
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/config.py --spec tools/t2_mutations.json
```

The runner requires a committed, clean, readable working tree and passing baseline tests. It changes only the target file, requires the expected failing test with pytest exit code 1, restores with `git restore`, and checks clean status after each mutation. It writes the current invocation's evidence to `.venv/mutation-results.json`; add `--list` to preview or `--start N --end M` for a subset.

#### T2 contract check

All implementation functions below are in `src/council/config.py`; tests are in `tests/test_config.py`. Data-contract shapes remain in the T1 models. These checks validate configuration, not the downstream behavior that consumes it.

| Contract rule/field | Implementation | Tests |
|---|---|---|
| Section 11 `max_rounds` | `MAX_ROUNDS`, `load_config`: constant 2, reject a YAML setting even when its value is 2 | `test_load_config`, `test_max_rounds_is_not_a_setting` |
| Section 11 configuration structure/types | `load_config` uses safe YAML, rejects duplicates/non-mappings, validates required/extra fields and strict types; reports ConfigError | `test_load_config`, `test_invalid_yaml`, `test_missing_file`, `test_duplicate_key_in_valid_config`, `test_bad_value_has_field_path` |
| `max_total_tokens`, `max_calls`, `max_seconds_total` | `validate_budget`: positive totals, starting values preserved in config.yaml | `test_bad_value_has_field_path`, `test_tunable_values_and_missing_resource_files` |
| `max_tokens_per_call`: specialist, judge, red_team, chair | `validate_budget`: positive output caps | `test_bad_value_has_field_path`, `test_load_config` |
| `chair_reserve`: tokens, seconds, calls | `validate_budget`: positive, smaller than corresponding total; token reserve covers chair output cap | `test_bad_value_has_field_path` |
| `max_repair_retries_per_turn`, `max_api_attempts` | `validate_limits`: 1 repair and 2 API attempts; config.yaml retry wait must be nonnegative | `test_bad_value_has_field_path` |
| `retrieval_top_k`; section 2 IDs; config.yaml `retrieval.case_sections` | `validate_limits`: top_k=5 and nonempty selection of known CASE section IDs | `test_bad_value_has_field_path`, `test_load_config` |
| `quote_words` / section 13 rule 4 | `validate_limits`: min 4, max 40; actual quote matching remains T5 | `test_bad_value_has_field_path` |
| `judge_disagreement_gap`, `judge_feedback` | `validate_limits`: gap 2, max 5 notes, max 40 words; scoring/truncation remain T6/T11 | `test_bad_value_has_field_path` |
| `temperature`: specialist, judge, red_team, chair | `validate_limits` and Config's finite-number validation: nonnegative finite values; retain configured values | `test_bad_value_has_field_path`, `test_tunable_values_and_missing_resource_files` |
| `models`: specialist/chair share one; judges share a different one | `validate_models`: configured nonblank provider/model identities, reject TBD, compare both provider and model | `test_bad_value_has_field_path`, `test_judges_differ_from_specialists`, `test_checked_in_placeholders_explain_what_to_fill` |
| Section 1 role codes; config.yaml `roles` | `validate_roles`: exactly SURG, PHYS, ANAES, ADMIN, RED, nonblank name/KB/keywords, specialist persona filename | `test_required_roles`, `test_unknown_role`, `test_bad_value_has_field_path` |
| config.yaml `paths.cases`, `paths.runs`, `paths.prompts` | `validate_roles`: nonblank path text; no filesystem existence requirement at this stage | `test_bad_value_has_field_path`, `test_tunable_values_and_missing_resource_files` |
| Section 13 rules 10 and 12 | Only validates budget/reserve settings here; gateway enforcement and locks remain T7/T8 | No claim of runtime enforcement in T2 |

No contract changes were made. The checked-in placeholder configuration is intentionally not ready for a live run. Human review should confirm the model selections before later provider work and review the fixed-limit versus tunable-budget policy above.

#### T2 mutation table

Each row below ran against committed `src/council/config.py`, triggered a test failure, and was restored with clean Git status before the next mutation. Parameterized failures are listed by test function for readability.

| Rule | What was broken | Test that failed |
|---|---|---|
| Exactly two rounds | `MAX_ROUNDS: Final = 2 -> MAX_ROUNDS: Final = 3` | `test_load_config` |
| Reject duplicate YAML keys | `if duplicate: -> if False:` | `test_duplicate_key_in_valid_config` |
| Strict setting types | `Config.model_validate(data, strict=True) -> Config.model_validate(data, strict=False)` | `test_bad_value_has_field_path` |
| Validate loaded policy | `validate_config(config) -> # skipped policy validation` | `test_bad_value_has_field_path` |
| Positive budgets | `getattr(budget, field) > 0 -> True` | `test_bad_value_has_field_path` |
| Positive output caps | `require(cap > 0, -> require(True,` | `test_bad_value_has_field_path` |
| Reserve within budget | `0 < reserve < total -> True` | `test_bad_value_has_field_path` |
| Reserve covers chair cap | `budget.chair_reserve.tokens >= budget.max_tokens_per_call.chair -> True` | `test_bad_value_has_field_path` |
| Fixed retries.max_repair_retries_per_turn | `"retries.max_repair_retries_per_turn": (config.retries.max_repair_retries_per_turn, 1), -> # removed retries.max_repair_retries_per_turn` | `test_bad_value_has_field_path` |
| Fixed retries.max_api_attempts | `"retries.max_api_attempts": (config.retries.max_api_attempts, 2), -> # removed retries.max_api_attempts` | `test_bad_value_has_field_path` |
| Fixed retrieval.top_k | `"retrieval.top_k": (config.retrieval.top_k, 5), -> # removed retrieval.top_k` | `test_bad_value_has_field_path` |
| Fixed grounding.quote_words_min | `"grounding.quote_words_min": (config.grounding.quote_words_min, 4), -> # removed grounding.quote_words_min` | `test_bad_value_has_field_path` |
| Fixed grounding.quote_words_max | `"grounding.quote_words_max": (config.grounding.quote_words_max, 40), -> # removed grounding.quote_words_max` | `test_bad_value_has_field_path` |
| Fixed judging.disagreement_gap | `"judging.disagreement_gap": (config.judging.disagreement_gap, 2), -> # removed judging.disagreement_gap` | `test_bad_value_has_field_path` |
| Fixed judging.feedback_max_notes | `"judging.feedback_max_notes": (config.judging.feedback_max_notes, 5), -> # removed judging.feedback_max_notes` | `test_bad_value_has_field_path` |
| Fixed judging.feedback_max_words | `"judging.feedback_max_words": (config.judging.feedback_max_words, 40), -> # removed judging.feedback_max_words` | `test_bad_value_has_field_path` |
| Nonnegative retry wait | `config.retries.api_retry_wait_seconds >= 0 -> True` | `test_bad_value_has_field_path` |
| Nonnegative temperature | `temperature >= 0 -> True` | `test_bad_value_has_field_path` |
| Known retrieval sections | `bool(config.retrieval.case_sections) and set(config.retrieval.case_sections) <= CASE_SECTIONS -> True` | `test_bad_value_has_field_path` |
| Required council roles | `set(config.roles) == SPECIALISTS \| {Role.RED} -> True` | `test_required_roles` |
| Nonblank resource paths | `bool(path.strip()) -> True` | `test_bad_value_has_field_path` |
| Nonblank role fields | `bool(getattr(settings, field).strip()) -> True` | `test_bad_value_has_field_path` |
| Role keywords | `bool(settings.keywords) and all(word.strip() for word in settings.keywords) -> True` | `test_bad_value_has_field_path` |
| Specialist persona | `bool(settings.persona_prompt and settings.persona_prompt.strip()) -> True` | `test_bad_value_has_field_path` |
| Configured model identities | `bool(value.strip()) and value.strip().upper() != "TBD" -> True` | `test_bad_value_has_field_path` |
| Chair shares specialist model | `getattr(models.chair, field) == getattr(models.specialist, field) -> True` | `test_bad_value_has_field_path` |
| Judges share their model | `getattr(models.judge_a, field) == getattr(models.judge_b, field) -> True` | `test_bad_value_has_field_path` |
| Judges differ from specialists | `models.judge_a != models.specialist -> True` | `test_judges_differ_from_specialists` |


Human review starting points:

1. `src/council/config.py` - `load_config`: safe loading and actionable errors.
2. `src/council/config.py` - `validate_limits`: the fixed contract values.
3. `tests/test_config.py` - `test_bad_value_has_field_path`: rejected settings and their error messages.
