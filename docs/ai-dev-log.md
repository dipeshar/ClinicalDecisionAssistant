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
| T3 | Added template ingestion and four-group injection scanning with synthetic clean/attack fixtures. | 705 tests pass; all 33 mutations detected and restored; contract mapping below. | Paused for preamble clarification; human approved rejection. Added an independent exact-tag assertion during review. | |
| T3b | Applied the exact authorized preamble/privacy documentation updates, then added the ingest privacy guard, config policy, safe rejection trace and reusable identifier list. | 774 tests pass; 32 mutations detected and restored in an isolated committed checkout. | Fixed a Windows line-ending assertion and updated the model-audit count for the new config shape. Existing architecture edits were preserved. | |
| T4 | Built KB validation, shared privacy scanning, deterministic BM25 retrieval and Round 1/2 query construction using synthetic test fixtures only. | 808 tests pass; all 42 final mutations detected and restored. Clinical demonstration passed; added email was rejected without exposing it. | The Round 1 isolation mutation initially failed a different test than expected; strengthened its regression fixture and repeated successfully. | |
| T5 | Implemented isolated quote normalization, source/turn checks, citation verification and current claim grounding checks. | 838 tests pass; all 33 mutations detected and restored. Every requested quote rule has a separate named test. | No test failures or surviving mutations during implementation/audit. The requested quote rule is rule 4 in section 13, rather than section 4. | |
| T6 | Implemented final-argument selection, dissent, strict-majority warning and confidence formula. | 892 tests pass; all 45 committed-code mutations detected and restored; contract mapping below. | Initially stopped on two contract gaps, resolved by the human. Discarded stale doc edits only with explicit authorization. Corrected one test fixture arithmetic error. | |
| T7 | Reviewed a prior session's unfinished draft of `budget.py`/`trace.py` as a pull request against the contracts, then ran the tests and the full end-of-task routine myself (nothing from the draft was assumed correct). | 929 tests pass; all 44 committed-code mutations (33 budget, 11 trace) detected and restored; contract mapping below. The existing race test (32 threads, configurable `--race-iterations`, default 25) was re-run at 300 iterations/thread (9600 calls) to confirm the concurrency requirement holds at a meaningful scale, not just the default. | The draft had no dev-log entry, no mutation run, and the mutation spec/test files were still untracked, so the mutation tool's clean-tree/`git restore` check could not run until the code and specs were committed first (matching the T6 precedent of committing the spec file before auditing). No code changes were needed; the draft matched the contracts. | |
| T8 | Implemented `gateway.py` (`LLMGateway`) and `providers/base.py`/`providers/fake.py`, plus the four extra rules requested: privacy check before the budget check, an import-graph test restricting provider SDKs to `providers/`, an API-key-leak test, and a scripted `FakeProvider`. | 956 tests pass; all 30 committed-code mutations (24 gateway, 6 fake provider) detected and restored; contract mapping below. | A crude tokens-in estimate (`len(prompt) // 4`) let real usage exceed the budget reservation and crash `Budget.complete`; switched to `len(prompt)` (a safe upper bound, since no tokenizer produces more tokens than characters) so the reservation can never be undersized. The first version of the tiny-budget mutation test didn't discriminate a `tokens_in`-zeroing mutation, because the output cap alone already exceeded that budget's limit; added a budget sized so the cap fits alone but not with a long prompt, and updated the mutation spec to point at it before re-auditing. Retry now also covers rate limits (`ProviderRateLimit`), not just timeouts, matching design.md's "timeouts and rate limits" wording; the original draft-style plan only had a timeout subtype. | |
| T1 addendum | Checkpoint A found `Report` was missing the `privacy_summary: PrivacySummary` field that `data-contracts.md` section 8 requires (added to the contracts by `4f4db15`, after T1 was first committed, and never picked up since). Added the `PrivacySummary` model and the `Report` field, following the same pattern as `JudgeSummary`/`ConfidenceInputs`. | 965 tests pass. Re-running the full built-in T1 mutation plan (117 rules; bumped from 116, pinned by `test_mutation_check.py::test_t1_plan`) first found a genuine tool bug: 2 real kills (`Exact enum Role`, `Shape Argument`) scored `SURVIVED/ERROR` because both crash pytest collection rather than producing an ordinary `FAILED` test, which the tool didn't recognize as a kill. Fixed the tool (`tools/mutation_check.py`, commit `27aadb7`) to treat any nonzero pytest exit code as a kill, added a self-test, then re-ran: **117 / 117 `KILLED`**, entirely by the tool itself. | See the tool-bug writeup below: the bug could only undercount kills, never overcount, so no earlier task's reported mutation numbers need re-checking. |

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

### T3: ingestion and scanner audit

Implemented `ingest_case`, fixed heading recognition, original-byte SHA-256, missing-heading reporting, and code-owned section/flag fields. `SCANNER_PATTERNS` in `src/council/scanner.py` is the single human-readable pattern list: instruction override, role spoofing, answer manipulation, and hidden text. `scan_section` retains original text and line endings, tags each flagged line once, and records matching groups with original one-based file line numbers. Multiline matches flag every affected line.

The small synthetic fixtures in `tests/fixtures/cases/` cover a clean case and an injection case. The realistic Consultant Review saying ?I recommend proceeding with surgery? and the Medications section remain unflagged. Attack tests cover the requested examples, fake system lines, HTML comments, hidden HTML and invisible characters. No model calls, network access, dependencies, protected-document edits, or T4 work.

What went wrong / uncertainty:

- T3 paused because preamble text cannot be cited, but injection flags need a section ID. The human explicitly approved rejecting suspicious title/preamble text with its original line number. Attacks inside sections are retained and tagged.
- Review found that tests importing the tag constant did not independently verify its spelling. Added a literal assertion, committed it, and confirmed a changed tag fails it. No mutation survived the completed audit.
- Sandbox restrictions on pytest temporary directories and Git required approved elevated test, commit and mutation commands. Pytest caching was disabled. Nothing was installed.
- This is a heuristic scanner, not proof that every attack is detected or every clinical sentence is safe. The requested examples and realistic negative cases are covered. Prompt delimiters, red-team interpretation, trace integration and safe report rendering belong to later tasks.
- Implementation conventions: `case_id` uses the filename stem, `source_file` preserves the supplied Path spelling, and `title` is the nonempty text after `# Case:`. These fields have no further contract format. A UTF-8 BOM is accepted for parsing but remains part of the file hash. No T3 field knowingly differs from its written contract.

Re-run from the repository root (mutation checks require a clean committed working tree):

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/scanner.py --spec tools/t3_scanner_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/ingest.py --spec tools/t3_ingest_mutations.json
```

Each mutation runs the full suite, requires a named failing test, restores the file with `git restore`, and requires clean Git status before continuing. All 15 scanner and 18 ingestion mutations were detected. The exact-tag mutation was checked after its additional test commit. The runner overwrites `.venv/mutation-results.json` each invocation; this table preserves both audits.

#### T3 contract check

Tests below are in `tests/test_ingest.py`, except names prefixed ?scanner? in `tests/test_scanner.py`.

| Contract rule or field | Implementation | Test |
|---|---|---|
| Section 1 case IDs; section 2 eight exact heading/ID mappings | `ingest.CASE_HEADINGS`, `find_headings`, `ingest_case` | `test_clean_case_and_clinical_sections` |
| Section 2 template-only parsing and missing headings | `find_headings`, `ingest_case` | `test_ambiguous_headings_rejected`, `test_missing_sections_and_empty_existing_section`, `test_no_sections_reports_all_missing` |
| CaseSection.id | `ingest_case` heading lookup | `test_clean_case_and_clinical_sections` |
| CaseSection.heading | `find_headings`, `ingest_case` | `test_clean_case_and_clinical_sections` |
| CaseSection.text: exact body except required tag | `ingest_case`, `scan_section`, `FLAG_TAG` | `test_byte_hash_and_text_preservation`, `test_missing_sections_and_empty_existing_section`, `test_injection_case_preserves_and_tags_evidence`; scanner `test_four_reviewable_groups`, `test_multiline_hidden_text_and_original_line_numbers` |
| CaseSection.flagged | `ingest_case` from scanner flags | `test_clean_case_and_clinical_sections`, `test_injection_case_preserves_and_tags_evidence` |
| CaseSection.flag_reasons | `ingest_case` unique matched groups | `test_injection_case_preserves_and_tags_evidence`; scanner `test_split_instruction_and_multiple_reasons` |
| CaseContext.case_id | `ingest_case` filename stem | `test_clean_case_and_clinical_sections` |
| CaseContext.source_file | `ingest_case` Path string | `test_clean_case_and_clinical_sections` |
| CaseContext.case_hash: original-file SHA-256 | `ingest_case` hashes raw bytes before parsing | `test_byte_hash_and_text_preservation`, `test_injection_case_preserves_and_tags_evidence` |
| CaseContext.title | `read_title`, `ingest_case` | `test_clean_case_and_clinical_sections`, `test_unreadable_invalid_utf8_and_missing_title` |
| CaseContext.sections | `ingest_case` ordered CaseSections | `test_clean_case_and_clinical_sections`, `test_missing_sections_and_empty_existing_section` |
| CaseContext.missing_sections: heading names | `ingest_case` expected minus present | `test_missing_sections_and_empty_existing_section`, `test_no_sections_reports_all_missing` |
| CaseContext.injection_flags | `ingest_case` collects scanner flags | `test_injection_case_preserves_and_tags_evidence` |
| InjectionFlag.section_id | `scan_section` receives mapped ID | scanner `test_attack_groups`; `test_injection_case_preserves_and_tags_evidence` |
| InjectionFlag.line_number | `scan_section` original-line offsets from ingest | scanner `test_multiline_hidden_text_and_original_line_numbers`; `test_injection_case_preserves_and_tags_evidence` |
| InjectionFlag.matched_pattern | `scan_section` named group | scanner `test_attack_groups`, `test_split_instruction_and_multiple_reasons` |
| Section 3: all fields code-owned | Ingest/scanner construct T1 models without LLM calls | `test_clean_case_and_clinical_sections` field assertions and JSON round trip; attack integration test |
| Section 7 downstream scanner count / flagged citations | T3 supplies flags only; red-team aggregation and citation matching belong to T13 | Deferred to T13 |

Additional design/user rules: scanner `test_attack_groups` covers the four groups; `test_clinical_language_not_flagged` and the clean-case integration test cover clinical language; `test_suspicious_preamble_rejected` covers the human-approved preamble policy. Ingest errors propagate explicitly as `IngestError`; trace/orchestration integration remains future work.

#### T3 mutation table

| Rule | What was broken | Which test failed |
|---|---|---|
| Detect instruction_override | `for name, pattern in SCANNER_PATTERNS.items(): -> for name, pattern in SCANNER_PATTERNS.items(): /         if name == 'instruction_override': /             continue` | `tests/test_scanner.py::test_attack_groups` |
| Detect role_spoofing | `for name, pattern in SCANNER_PATTERNS.items(): -> for name, pattern in SCANNER_PATTERNS.items(): /         if name == 'role_spoofing': /             continue` | `tests/test_scanner.py::test_attack_groups` |
| Detect answer_manipulation | `for name, pattern in SCANNER_PATTERNS.items(): -> for name, pattern in SCANNER_PATTERNS.items(): /         if name == 'answer_manipulation': /             continue` | `tests/test_scanner.py::test_attack_groups` |
| Detect hidden_text | `for name, pattern in SCANNER_PATTERNS.items(): -> for name, pattern in SCANNER_PATTERNS.items(): /         if name == 'hidden_text': /             continue` | `tests/test_scanner.py::test_attack_groups` |
| Normal clinical language is not flagged | `for match in re.finditer(pattern, text, -> for match in re.finditer(pattern + r'\|recommend', text,` | `tests/test_scanner.py::test_clinical_language_not_flagged` |
| Case insensitive matching | `flags=re.IGNORECASE \| re.MULTILINE -> flags=re.MULTILINE` | `tests/test_scanner.py::test_attack_groups` |
| One tag per flagged line | `lines[index] = FLAG_TAG + " " + lines[index] -> lines[index] = lines[index]` | `tests/test_scanner.py::test_attack_groups` |
| Preserve original line endings | `text.splitlines(keepends=True) -> text.splitlines(keepends=False)` | `tests/test_scanner.py::test_multiline_hidden_text_and_original_line_numbers` |
| Flag every line in a hidden span | `range(first, last + 1) -> range(first, first + 1)` | `tests/test_scanner.py::test_multiline_hidden_text_and_original_line_numbers` |
| Deduplicate group on each line | `if name not in reasons: -> if True:` | `tests/test_scanner.py::test_split_instruction_and_multiple_reasons` |
| Flag original line number | `line_number=start_line + index -> line_number=start_line + index + 1` | `tests/test_scanner.py::test_attack_groups` |
| Flag section ID | `section_id=section_id -> section_id='CASE-profile'` | `tests/test_scanner.py::test_attack_groups` |
| Flag pattern name | `matched_pattern=name -> matched_pattern='wrong'` | `tests/test_scanner.py::test_attack_groups` |
| Require one-based offsets | `if start_line < 1: -> if False:` | `tests/test_scanner.py::test_empty_text_and_line_number_validation` |
| Exact contract warning tag | `FLAG_TAG: Final = "[FLAGGED: possible instruction]" -> FLAG_TAG: Final = "[warning]"` | `tests/test_scanner.py::test_four_reviewable_groups` |
| Fixed section IDs | `"Patient Profile": "CASE-profile" -> "Patient Profile": "CASE-wrong"` | `tests/test_ingest.py::test_clean_case_and_clinical_sections` |
| Preserve section heading | `id=section_id, heading=heading -> id=section_id, heading='wrong'` | `tests/test_ingest.py::test_clean_case_and_clinical_sections` |
| Case ID is file stem | `case_id=source.stem -> case_id=source.name` | `tests/test_ingest.py::test_clean_case_and_clinical_sections` |
| Source file path | `source_file=str(source) -> source_file=source.name` | `tests/test_ingest.py::test_clean_case_and_clinical_sections` |
| Title from preamble | `title=title, -> title='wrong',` | `tests/test_ingest.py::test_clean_case_and_clinical_sections` |
| Hash original bytes | `sha256(raw).hexdigest() -> sha256(text.encode()).hexdigest()` | `tests/test_ingest.py::test_byte_hash_and_text_preservation` |
| Exact section body | `lines[index + 1:end] -> lines[index:end]` | `tests/test_ingest.py::test_missing_sections_and_empty_existing_section` |
| Missing headings list | `if heading not in present -> if False` | `tests/test_ingest.py::test_missing_sections_and_empty_existing_section` |
| Code-owned flagged marker | `flagged=bool(section_flags) -> flagged=False` | `tests/test_ingest.py::test_injection_case_preserves_and_tags_evidence` |
| Section flag reasons | `list(dict.fromkeys(flag.matched_pattern for flag in section_flags)) -> []` | `tests/test_ingest.py::test_injection_case_preserves_and_tags_evidence` |
| Context injection flags | `flags.extend(section_flags) -> flags.extend([])` | `tests/test_ingest.py::test_injection_case_preserves_and_tags_evidence` |
| Absolute original line offsets | `start_line=index + 2 -> start_line=index + 1` | `tests/test_ingest.py::test_injection_case_preserves_and_tags_evidence` |
| Reject suspicious preamble | `if flags: -> if False:` | `tests/test_ingest.py::test_suspicious_preamble_rejected` |
| Reject unknown headings | `if heading not in CASE_HEADINGS: -> if False:` | `tests/test_ingest.py::test_ambiguous_headings_rejected` |
| Reject duplicate headings | `if heading in seen: -> if False:` | `tests/test_ingest.py::test_ambiguous_headings_rejected` |
| Require template heading order | `if headings and order.index(heading) < order.index(headings[-1][1]): -> if False:` | `tests/test_ingest.py::test_ambiguous_headings_rejected` |
| Require title | `if not first_line.startswith("# Case:") or not first_line.removeprefix("# Case:").strip(): -> if False:` | `tests/test_ingest.py::test_unreadable_invalid_utf8_and_missing_title` |
| Reject invalid UTF-8 | `raw.decode("utf-8-sig") -> raw.decode("utf-8-sig", errors="replace")` | `tests/test_ingest.py::test_unreadable_invalid_utf8_and_missing_title` |

Human review starting points:

1. `src/council/scanner.py` - `scan_section` and adjacent `SCANNER_PATTERNS`: matching, preservation, and false-positive tradeoffs.
2. `src/council/ingest.py` - `ingest_case`: exact bodies, original-byte hash and flag propagation.
3. `tests/test_ingest.py` - `test_clean_case_and_clinical_sections`: realistic Consultant Review and Medications regression fixture.

### T3b: privacy guard at ingest

Documentation commits, in the requested order:

- `56b3d1d` - `Docs: text outside the sections`. Confirmed T3 was complete through `b405ceb`; `read_title` already rejected flagged preamble/title lines before building a CaseContext. Added the three exact statements supplied by the human.
- `4f4db15` - `Docs: privacy barriers`. Applied the patch payloads without rewording after verifying the replacement text and anchors. B1 immediately follows the new preamble paragraph. The supplied patch was previously untracked, so this commit also recorded it to make its deletion auditable.
- `a51aabf` - `Docs: remove applied privacy patch`. Deleted the patch in its own commit.

T3b implementation was committed as `1303cfa` before mutation checking. `privacy.IDENTIFIER_PATTERNS` is the one commented identifier list for ingest and later gateway reuse. It covers all nine contract kinds; national formats include Aadhaar-like, PAN-like and SSN-like shapes. It deliberately blocks fabricated identifiers as well as real-looking ones. `scan_identifiers` returns only kind and original one-based line number, never a captured value.

`ingest_case(path, config)` now requires config. It checks privacy immediately after decoding the original bytes, before headings, injection scanning, or CaseContext construction. The configured marker must occur in the preamble, ignoring case; a marker appearing only in section text is insufficient. Normal clinical numbers, doses, blood pressure, ages, dates, times, and recommendations have negative tests. Existing T3 tests use a custom marker to retain their original line-number assertions; the new tests exercise the configured template marker.

A rejection writes one `TraceEvent` into a new run folder under `config.paths.runs`. The existing `error` field holds kind and line number; safe trace metadata is retained, content-bearing fields are null, and tokens are zero. No run bundle or report containing rejected data is created. The folder name uses a generated rejection identifier, not the source filename or title. Sequence assignment and writing are under a lock; the general T7 trace subsystem is not implemented here. Failed trace writes still block ingest and suppress the underlying filesystem exception, which could contain sensitive paths.

Config loading now requires `PrivacyConfig.synthetic_marker` and `approved_providers`. The marker must be nonblank; approved names cannot be blank or padded. Every configured role's provider must be an exact member of the list. The existing refusal of unresolved TBD models remains. `EventType` includes `privacy_block`; the contract round-trip/required-field tests cover the new config shape.

What went wrong and limitations:

- The earlier patch attempt stopped correctly because its preamble anchor did not exist. The human supplied exact text and authorized the repair before this implementation.
- The first T3b run had two failures: a test expected LF although Windows wrote CRLF, and the generic model mutation-plan count was still 115. The fixture now writes exact bytes, and the count is 116 because PrivacyConfig adds a shape. Final tests pass.
- Pattern review explicitly added local and international phone examples and ensured a time such as 10:30:00 is not mistaken for IPv6. The final pattern comment was clarified to mention local seven-digit phone shapes; no runtime behavior changed after the audit.
- Format heuristics cannot establish that data is synthetic or detect arbitrary names in prose. Long numbers currently mean eight or more consecutive digits; compact numeric dates can therefore be rejected conservatively. Ordinary separated dates are tested. More real-world formats may need reviewed patterns and tests.
- A missing marker has no matched line: the safe error uses kind `missing_marker` and line 1 (start of preamble). When several identifiers match, the first by physical line and pattern-list order supplies the single rejection event. No matched value is retained in a finding or error.
- Trace kind/line are encoded in the existing `TraceEvent.error` field, preserving section 10's shape rather than adding unspecified fields. A fresh synthetic rejection ID avoids leaking an identifier in a case filename.
- Your architecture Markdown/SVG/PNG edits remained untouched and uncommitted. Mutation checks used a detached worktree at the implementation commit, so every restore and clean-status check applied to a clean tree without hiding your edits. Tests used the existing project virtual environment; no installs or network access.

#### T3b contract check

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 3 / rule 19: required configured marker, preamble only, case-insensitive | `privacy.check_case_privacy`, `ingest.ingest_case` | `test_marker_is_required_in_preamble`, `test_normal_case_and_case_insensitive_marker` |
| Section 3: scan whole file, including title, preamble and headings | `privacy.scan_identifiers` before `find_headings` | `test_rejects_identifiers_everywhere_before_parsing` (five locations, including comment) |
| Section 3 identifier kinds: email, phone, national_id, long_number, date_of_birth, url, ip_address, id_label, name_label | `privacy.IDENTIFIER_PATTERNS`, `scan_identifiers` | `test_identifier_kinds`, `test_pattern_list_is_complete` |
| Rule 19: no matched value in errors or trace, no CaseContext on rejection | `PrivacyHit`, `ingest_case`, `write_privacy_rejection` | `test_rejects_identifiers_everywhere_before_parsing`, `test_identifier_kinds`, `test_trace_write_failure_is_redacted_and_still_blocks` |
| Section 3: one privacy_block event, no case text in rejected run | `write_privacy_rejection` writes only trace.jsonl | `rejection_trace`, called by all ingest privacy-rejection tests |
| Section 10: event_type privacy_block | `models.EventType`, `write_privacy_rejection` | `test_enum_values`, `rejection_trace` |
| Section 10: run_id, seq, timestamp, step | generated metadata and seq=1 under `_REJECTION_LOCK` | `rejection_trace`, `test_first_hit_only_and_distinct_rejection_folders`; T1 `test_contract_round_trip_and_fields[TraceEvent]` covers wire shape |
| Section 10: role, round, model, prompt, retrieved_passage_ids, raw_output, parsed_ref | all null on rejection | `rejection_trace` |
| Section 10: tokens_in, tokens_out, budget_tokens_used | all zero on rejection | `rejection_trace` |
| Section 10: latency_ms, attempt, repair | null, 1, false for this pre-call event | T1 TraceEvent shape tests; `rejection_trace` validates serialized TraceEvent |
| Section 10: error | safe kind and original line number | `test_rejects_identifiers_everywhere_before_parsing`, `test_marker_is_required_in_preamble` |
| Section 11: privacy.synthetic_marker and privacy.approved_providers | `models.PrivacyConfig`, `Config.privacy`, `config.validate_privacy` | `test_invalid_privacy_config`, `test_privacy_section_required`, T1 shape/required-field tests |
| Section 11: every configured model provider approved | `config.validate_models` | `test_each_provider_must_be_approved` across all five model roles |
| Rule 22: one reusable pattern list | `IDENTIFIER_PATTERNS`, public `scan_identifiers` API | `test_pattern_list_is_complete`, identifier-kind tests; gateway reuse remains T8 |
| Section 14: rejected run folder and trace | `write_privacy_rejection` under configured runs path | `rejection_trace`, `test_first_hit_only_and_distinct_rejection_folders` |

No T3b requirement is knowingly implemented differently from the contract. The new section 8 `Report.privacy_summary` / `PrivacySummary` report work remains for T14/T19; those model/report changes are not included in this ingest task. Rule 20's outbound gateway checks and rule 21's fake-key/output tests remain T8 and later run/report work. No gateway, report, provider or T4 feature was started. No real model calls are possible in these ingest tests; FakeProvider belongs to T8.

#### T3b mutation check

Run each command from a clean checkout using the project's virtual-environment Python:

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/privacy.py --spec tools/t3b_privacy_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/ingest.py --spec tools/t3b_ingest_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/config.py --spec tools/t3b_config_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/models.py --spec tools/t3b_models_mutations.json
```

For this audit, the detached checkout was `.venv/t3b-audit`, and the interpreter was the main checkout's `.venv/Scripts/python.exe`. Pytest's configured `pythonpath = ["src"]` loaded the isolated source. Every deliberate break ran the full suite, produced the expected failing test, was undone with `git restore`, and was followed by a clean Git status check. All 32 were detected; no new test was needed for a surviving mutation. The runner overwrites `.venv/mutation-results.json` each invocation; this table preserves all four runs.

| Rule | What was broken | Which test failed |
|---|---|---|
| Detect email | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'email' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect phone | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'phone' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect national_id | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'national_id' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect long_number | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'long_number' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect date_of_birth | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'date_of_birth' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect url | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'url' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect ip_address | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'ip_address' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect id_label | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'id_label' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Detect name_label | `if re.search(pattern, line, flags=re.IGNORECASE): -> if kind != 'name_label' and re.search(pattern, line, flags=re.IGNORECASE):` | `tests/test_privacy.py::test_identifier_kinds` |
| Ordinary clinical values pass | `if re.search(pattern, line, flags=re.IGNORECASE): -> if re.search(pattern, line, flags=re.IGNORECASE) or "150/90" in line:` | `tests/test_privacy.py::test_clinical_values_are_not_identifiers` |
| Original one-based line numbers | `enumerate(text.splitlines(), start=1) -> enumerate(text.splitlines(), start=2)` | `tests/test_privacy.py::test_identifier_kinds` |
| Case-insensitive identifier scan | `flags=re.IGNORECASE -> flags=0` | `tests/test_privacy.py::test_identifier_kinds` |
| Require the configured marker | `if not synthetic_marker.strip() or synthetic_marker.casefold() not in "\n".join(preamble).casefold(): -> if False:` | `tests/test_privacy.py::test_marker_is_required_in_preamble` |
| Marker must be in preamble | `preamble = preamble[:index] -> preamble = preamble` | `tests/test_privacy.py::test_marker_is_required_in_preamble` |
| Marker ignores case | `synthetic_marker.casefold() not in -> synthetic_marker not in` | `tests/test_privacy.py::test_normal_case_and_case_insensitive_marker` |
| Reject blank marker defensively | `not synthetic_marker.strip() or -> False or` | `tests/test_privacy.py::test_marker_is_required_in_preamble` |
| First hit only | `return hits[0] -> return hits[-1]` | `tests/test_privacy.py::test_first_hit_only_and_distinct_rejection_folders` |
| Privacy event type | `event_type=EventType.PRIVACY_BLOCK -> event_type=EventType.ERROR` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| No prompt data in rejection trace | `prompt=None, -> prompt="unsafe data",` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Zero tokens spent | `tokens_in=0, tokens_out=0 -> tokens_in=1, tokens_out=1` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Safe error includes kind and line | `error=f"{hit.kind} at line {hit.line_number}" -> error=None` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| One event per rejection | `stream.write(event.model_dump_json() + "\n") -> stream.write((event.model_dump_json() + "\n") * 2)` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Redact filesystem exception chain | `from None -> from OSError("fictional@example.invalid")` | `tests/test_privacy.py::test_trace_write_failure_is_redacted_and_still_blocks` |
| Privacy precedes parsing | `privacy_hit = check_case_privacy(text, config.privacy.synthetic_marker) -> privacy_hit = None` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Whole-file scan includes sections | `check_case_privacy(text, config.privacy.synthetic_marker) -> check_case_privacy(text.split("##", 1)[0], config.privacy.synthetic_marker)` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Write rejected-run audit | `write_privacy_rejection(config.paths.runs, privacy_hit) -> # skip rejected-run audit` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Exception must omit identifier value | `raise IngestError(f"{privacy_hit.kind} at line {privacy_hit.line_number}") -> raise IngestError(f"{privacy_hit.kind} at line {privacy_hit.line_number}: {text}")` | `tests/test_privacy.py::test_rejects_identifiers_everywhere_before_parsing` |
| Require nonblank synthetic marker | `bool(config.privacy.synthetic_marker.strip()) -> True` | `tests/test_config.py::test_invalid_privacy_config` |
| Approved names cannot be blank or padded | `all(name.strip() and name == name.strip() for name in config.privacy.approved_providers) -> True` | `tests/test_config.py::test_invalid_privacy_config` |
| Every configured provider must be approved | `choice["provider"] in config.privacy.approved_providers -> True` | `tests/test_config.py::test_each_provider_must_be_approved` |
| Required privacy config shape | `privacy: PrivacyConfig -> privacy: PrivacyConfig \| None = None` | `tests/test_config.py::test_privacy_section_required` |
| Privacy block enum value | `PRIVACY_BLOCK = "privacy_block" -> PRIVACY_BLOCK = "wrong"` | `tests/test_models.py::test_enum_values` |

Human review starting points:

1. `src/council/privacy.py` - `scan_identifiers` and the adjacent `IDENTIFIER_PATTERNS` list.
2. `src/council/ingest.py` - `ingest_case`, especially privacy rejection before parsing.
3. `tests/test_privacy.py` - `test_rejects_identifiers_everywhere_before_parsing`, including trace redaction checks.

### T4: KB loading and retrieval

Demonstration before any T4 edits (no files written):

```text
Clinical case: PASS; 8 sections; 0 injection flags.
Same case plus email: REJECTED: email at line 19
Address absent from rejection message and trace: confirmed.
```

The clinical section contained exactly: `BP 150/90, creatinine 2.4 mg/dL, eGFR 38, surgery on 14 March 2026, ICD-10 I25.1, heparin 5000 units`. The real `ingest_case` and rejection writer ran with file reads and directory/trace writes intercepted in memory; Python bytecode writing was disabled. The configured synthetic marker was present. All nine examples and exclusions in the plain-language identifier table were also checked against the actual patterns without writing files.

Implementation: `src/council/kb.py` loads all supplied role folders before exposing a searchable KB. It rejects duplicate IDs across files/folders, malformed IDs and wrong prefixes. It preserves passage bodies exactly, including whitespace and line endings, and uses the first level-one heading as source title. The shared identifier scanner checks every passage and its source title before length warnings or indexing. Privacy errors contain only a fixed explanation, file and valid passage ID; a sensitive filename is redacted, and malformed IDs are not echoed. No matched value appears in errors.

Lengths outside 40 through 150 whitespace-separated words produce `PassageLengthWarning`, not a loader error. Even an empty passage remains loadable with a warning; an entirely empty-token corpus receives zero retrieval scores rather than crashing BM25. Missing/empty folders, unreadable files and missing source titles produce explicit errors.

`tokenize` is the single tokenizer for documents and queries: Unicode casefold followed by alphanumeric tokens, splitting punctuation and underscores. BM25Okapi uses the installed rank-bm25 defaults. Results sort by descending score, then ascending passage ID, returning five or all available passages when fewer exist. IDs are sorted before index construction as well. Scores remain aligned with their passages, and retrieval only uses the requested role's KB.

`build_query` uses configured role keywords plus configured case-section bodies, never the case title or preamble. Round 2 additionally uses other roles' Round 1 summaries, then the text of own claims named by Round 1 judge untraceable-claim or claim-specific feedback entries. General notes, judge reasons, numeric scores, own summary and Round 2 arguments do not enter this query. Peer order is stable and flagged claims are deduplicated in original claim order. A successful own Round 1 argument is required for Round 2 retrieval.

`KnowledgeBase.round2_passages` provides the top-five results plus previously cited available passages from the same role's KB, without duplicates or changing RetrievalResult's scored top five. Case sections remain available separately via CaseContext. Unknown/foreign citation IDs name no available own-KB passage; they remain unchanged on the original claim for later grounding/repair and are not shown as evidence. This helper is ready for T12 prompt assembly; no prompting or grounding feature was implemented here.

Only `tests/fixtures/kb/` contains new KB Markdown (six surgeon passages and one physician passage). Additional malformed and boundary fixtures are generated by tests in temporary directories. No file under the real `kb/` was created or changed. The T4 task row was extended with the requested privacy-at-load rule and the other user constraints.

What went wrong / limits:

- Initial implementation tests passed. During mutations, forcing Round 2 context into Round 1 was caught by the Round 2 test, but not the named Round 1 regression. Its original inputs contained no peer summary or flagged claim, so they could not expose that mistake. Strengthened those inputs, committed `041f0c0`, then repeated that mutation and completed the audit. The production implementation did not need a change.
- Loader errors propagate as KBError; orchestration/trace integration belongs to later tasks. No real model/provider calls occur in this task, and no dependencies were installed.
- BM25 is lexical retrieval, not a relevance or clinical-correctness guarantee. The identifier scanner retains its documented format-only limitations. Passage word counts use whitespace splitting; retrieval tokens deliberately use the separate documented alphanumeric tokenizer.
- Your pre-existing architecture Markdown/SVG/PNG edits remained untouched. A detached audit checkout preserved them while allowing clean-status checks after every mutation.

#### T4 contract check

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 1: ROLE-KB-nn IDs, including RED | `read_passages` full-match and prefix checks | `test_wrong_prefix_and_malformed_ids`, `test_all_role_prefixes` |
| Task KB format: globally unique IDs | shared seen set in `load_kb` / `read_passages` | `test_duplicate_ids_rejected_globally` across same file, other files and roles |
| Passage.id | heading ID in `read_passages` | `test_load_exact_passages_and_role_fields` |
| Passage.kb | owning role code in `read_passages` | `test_load_exact_passages_and_role_fields`, `test_all_role_prefixes` |
| Passage.source_title | first level-one heading in `read_passages` | `test_load_exact_passages_and_role_fields` |
| Passage.text: exact original body | splitlines with endings retained; no strip/normalization | `test_load_exact_passages_and_role_fields`, `test_length_is_warning_only_with_exact_bounds` |
| RetrievalResult.role | `KnowledgeBase.retrieve` requested role and role index | `test_bm25_ranking_scores_and_role_isolation` |
| RetrievalResult.round | `retrieve` permits only 1 or 2 | `test_bm25_ranking_scores_and_role_isolation`, `test_invalid_round_and_failed_own_argument` |
| RetrievalResult.query; config role keywords and selected sections | `build_query`, preserved by `retrieve` | `test_round1_query_uses_only_keywords_and_configured_sections`, ranking test |
| Section 4 Round 2 query: peer summaries and own judge-flagged claim text | `build_query` | `test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Query inputs: Argument.argument_id, role, round, status, summary; Claim.claim_id and text; Score.argument_id, round, untraceable_claims.claim_id and feedback.claim_id | Round 1/own-role filtering and claim-ID selection in `build_query` | Round 2 query test, invalid/failed-own-argument test |
| Section 3: title/preamble never sent to agents | only CaseContext.sections contribute to query | exact query assertion in `test_round1_query_uses_only_keywords_and_configured_sections` |
| RetrievalResult.passages; section 11 top five | `KnowledgeBase.retrieve`, TOP_K=5 | ranking test, length test for fewer than five, deterministic tie test |
| RetrievalResult.scores: BM25 score for each passage | single sorted passage/score pairs in `retrieve` | manual expected BM25 value and JSON round trip in ranking test |
| Section 4 / rule 3: Round 1 cited passages available again in Round 2 | `round2_passages` reads Claim.citations.passage_id and unions known own-KB passages | `test_round2_carries_cited_passages_without_changing_top_five` |
| Rule 16: failed Round 1 argument does not proceed to Round 2 | query/carryover preconditions | `test_invalid_round_and_failed_own_argument`, carryover test |
| Rule 22 shared identifier list; user extension to KB load | existing `privacy.scan_identifiers`, called by loader | `test_shared_scan_is_used_on_every_passage`, privacy-rejection test, clinical-demo-text test |
| User: 40 to 150 words is warning only | `PassageLengthWarning` before indexing | boundary tests at 0, 39, 40, 150, 151 |
| User: deterministic ties and one simple tokenizer | `tokenize`, stable index order and score/ID sorting | `test_tokenizer_is_simple`, `test_same_tokenizer_for_corpus_and_query`, `test_ties_repeatably_sort_by_id_not_file_order` |
| User: privacy errors give file and passage ID only, never value | `safe_file_label`, safe loader errors without chained read exceptions | `test_privacy_rejection_contains_only_safe_location` |

No T4 contract field was knowingly implemented differently from its written requirement. The top-five RetrievalResult and the additional shown-passage union are kept separate; T12 must use the union when building Round 2 prompts. Quote verification remains T5; retrieval trace events remain later trace/orchestrator integration. No T5 work was started.

#### T4 mutation check

Re-run in a clean checkout with the project environment:

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/kb.py --spec tools/t4_mutations.json
```

The audit used `.venv/t4-audit` and the main checkout's virtual-environment interpreter. Pytest's configured src path loaded the isolated source. Mutations 0-25 passed on `156dab9`; after the stronger regression test commit, mutation 26 was repeated and 26-41 passed on `041f0c0`. Each break ran the full suite, produced the named test failure, was undone with `git restore`, and was followed by a clean Git status check. All 42 final checks detected the break. The table preserves results across the runner's per-invocation output overwrite.

| Rule | What was broken | Which test failed |
|---|---|---|
| Passage ID shape | `if not re.fullmatch(r"(?:SURG\|PHYS\|ANAES\|ADMIN\|RED)-KB-[0-9]{2}", passage_id): -> if False:` | `tests/test_kb.py::test_wrong_prefix_and_malformed_ids` |
| IDs globally unique | `if passage_id in seen: -> if False:` | `tests/test_kb.py::test_duplicate_ids_rejected_globally` |
| Correct role prefix | `if not passage_id.startswith(role.value + "-KB-"): -> if False:` | `tests/test_kb.py::test_wrong_prefix_and_malformed_ids` |
| Passage privacy scan | `if scan_identifiers(body) or scan_identifiers(titles[0]): -> if scan_identifiers(titles[0]):` | `tests/test_kb.py::test_privacy_rejection_contains_only_safe_location` |
| Title privacy scan | `if scan_identifiers(body) or scan_identifiers(titles[0]): -> if scan_identifiers(body):` | `tests/test_kb.py::test_privacy_rejection_contains_only_safe_location` |
| No identifier in rejection message | `raise KBError(f"KB privacy rejection: {label}: {passage_id}") -> raise KBError(f"KB privacy rejection: {label}: {passage_id}: {body}")` | `tests/test_kb.py::test_privacy_rejection_contains_only_safe_location` |
| Sensitive filename redaction | `return "[redacted filename]" if scan_identifiers(str(path)) else str(path) -> return str(path)` | `tests/test_kb.py::test_privacy_rejection_contains_only_safe_location` |
| Length warning lower bound | `not 40 <= count <= 150 -> not 39 <= count <= 150` | `tests/test_kb.py::test_length_is_warning_only_with_exact_bounds` |
| Length warning upper bound | `not 40 <= count <= 150 -> not 40 <= count <= 151` | `tests/test_kb.py::test_length_is_warning_only_with_exact_bounds` |
| Length is warning not error | `warnings.warn(f"passage outside 40 to 150 words: {label}: {passage_id}", /                           PassageLengthWarning, stacklevel=2) -> raise KBError("length is fatal")` | `tests/test_kb.py::test_length_is_warning_only_with_exact_bounds` |
| Exact passage text | `body = "".join(lines[index + 1:end]) -> body = "".join(lines[index + 1:end]).strip()` | `tests/test_kb.py::test_load_exact_passages_and_role_fields` |
| Passage KB role | `kb=role.value, -> kb="wrong",` | `tests/test_kb.py::test_load_exact_passages_and_role_fields` |
| Source title | `source_title=titles[0] -> source_title="wrong"` | `tests/test_kb.py::test_load_exact_passages_and_role_fields` |
| Title and headings required | `if not titles or not titles[0] or not headings: -> if False:` | `tests/test_kb.py::test_unreadable_empty_or_malformed_kb` |
| Only KB roles | `if role not in KB_ROLES: -> if False:` | `tests/test_kb.py::test_unreadable_empty_or_malformed_kb` |
| Tokenizer case folding | `text.casefold() -> text` | `tests/test_kb.py::test_tokenizer_is_simple` |
| Same corpus tokenizer | `corpus = [tokenize(p.text) for p in passages] -> corpus = [p.text.split() for p in passages]` | `tests/test_kb.py::test_same_tokenizer_for_corpus_and_query` |
| Same query tokenizer | `index.get_scores(tokenize(query)) -> index.get_scores(query.split())` | `tests/test_kb.py::test_same_tokenizer_for_corpus_and_query` |
| Top five | `TOP_K = 5 -> TOP_K = 4` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| Descending BM25 scores | `(-float(pair[1]), pair[0].id) -> (float(pair[1]), pair[0].id)` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| Ties by passage ID | `(-float(pair[1]), pair[0].id) -> (-float(pair[1]),)` | `tests/test_kb.py::test_ties_repeatably_sort_by_id_not_file_order` |
| Scores aligned with passages | `scores=[float(score) for _, score in ranked] -> scores=[0.0 for _, score in ranked]` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| Role isolation | `passages = self.passages[role] -> passages = self.passages[Role.PHYS]` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| Empty passage still retrievable | `BM25Okapi(corpus) if any(corpus) else None -> BM25Okapi(corpus)` | `tests/test_kb.py::test_length_is_warning_only_with_exact_bounds` |
| Role keyword query | `parts = [" ".join(config.roles[role].keywords)] -> parts = [""]` | `tests/test_kb.py::test_round1_query_uses_only_keywords_and_configured_sections` |
| Configured sections only | `parts.extend(sections[id] for id in config.retrieval.case_sections if id in sections) -> parts.extend(sections.values())` | `tests/test_kb.py::test_round1_query_uses_only_keywords_and_configured_sections` |
| Round 1 excludes peer and judge context | `if round == 2: -> if True:` | `tests/test_kb.py::test_round1_query_uses_only_keywords_and_configured_sections` |
| Round 2 uses only Round 1 arguments | `a for a in arguments if a.round == 1 -> a for a in arguments` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Other roles summaries only | `if a.role != role -> if True` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Only own Round 1 judge flags | `if score.round == 1 and score.argument_id == own[0].argument_id: -> if True:` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Untraceable claim flags | `flagged.update(note.claim_id for note in score.untraceable_claims) -> # omit untraceable claims` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Feedback claim flags | `flagged.update(note.claim_id for note in score.feedback if note.claim_id is not None) -> # omit feedback claims` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Only flagged claim text | `if claim.claim_id in flagged -> if True` | `tests/test_kb.py::test_round2_query_adds_peer_summaries_and_flagged_own_claims` |
| Successful own Round 1 needed | `if len(own) != 1 or own[0].status == "failed": -> if False:` | `tests/test_kb.py::test_invalid_round_and_failed_own_argument` |
| Carry cited passages into Round 2 | `shown.setdefault(id, available[id]) -> pass` | `tests/test_kb.py::test_round2_carries_cited_passages_without_changing_top_five` |
| Carryover only for correct role and round | `if result.round != 2 or own.round != 1 or own.role != result.role or own.status == "failed": -> if False:` | `tests/test_kb.py::test_round2_carries_cited_passages_without_changing_top_five` |
| RetrievalResult.role | `RetrievalResult(role=role, round=round, query=query, -> RetrievalResult(role=Role.RED, round=round, query=query,` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| RetrievalResult.round | `RetrievalResult(role=role, round=round, query=query, -> RetrievalResult(role=role, round=2, query=query,` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| RetrievalResult.query | `RetrievalResult(role=role, round=round, query=query, -> RetrievalResult(role=role, round=round, query="wrong",` | `tests/test_kb.py::test_bm25_ranking_scores_and_role_isolation` |
| Passage.id from heading | `Passage(id=passage_id, -> Passage(id="SURG-KB-99",` | `tests/test_kb.py::test_load_exact_passages_and_role_fields` |
| Only two rounds in query | `if round not in (1, 2): /         raise KBError -> if False: /         raise KBError` | `tests/test_kb.py::test_invalid_round_and_failed_own_argument` |
| Only two rounds in retrieval | `if round not in (1, 2): /             raise KBError -> if False: /             raise KBError` | `tests/test_kb.py::test_invalid_round_and_failed_own_argument` |

Human review starting points:

1. `src/council/kb.py` - `load_kb` / `read_passages`: global IDs, exact text, privacy and warnings.
2. `src/council/kb.py` - `build_query`: Round 1 and Round 2 inputs.
3. `src/council/kb.py` - `KnowledgeBase.retrieve`: BM25 scores, role isolation and ID tie-breaking.

### T5: quote verification

Implemented `src/council/grounding.py` and synthetic tests in `tests/test_grounding.py`; committed as `3f6a64e` before mutation checks. The contract quote rule is section 13, rule 4; section 5 specifies Citation and Claim fields. The user's twelve requested examples each have their own named test.

`normalize_quote_text` is the one normalization function. It folds case, collapses whitespace and translates curly single/double quotes and common hyphen/dash styles. Its only production caller is `quote_failure`, which uses it for both the quote and source. Retrieval's tokenizer and all stored source/quote text remain unchanged. A repository search confirmed there are no other production uses.

`quote_failure` splits on literal `...`, counts 4 through 40 words across the retained parts, and matches each part against the same source in order without overlap. It uses escaped literal matching with word-edge checks: a changed word cannot pass merely because it is a substring, and punctuation cannot act as a regex wildcard. Leading/trailing ellipses are allowed; empty or punctuation-only quotes fail the minimum count. Unicode ellipsis is not treated as the contract's three-dot skip operator.

`verify_citation` receives a code-owned registry of valid source IDs/text and the IDs actually shown in the current turn. Both existence and turn availability are checked before matching the quote. It constructs a fresh Citation with code-set source_type, verified and verify_note, preserving passage_id and quote exactly. Failure notes are fixed descriptions and never echo the quote, source text or untrusted ID. Unknown non-CASE IDs are classified as KB candidates for the two-valued source_type field, but cannot verify because they are absent from the registry. The registry must be built from validated case sections/KB passages, never model output.

`ground_claim` copies the caller-assigned claim_id and draft text, verifies all citations, and marks the current result grounded only when there is at least one citation and all pass. Rechecking a repaired draft recomputes the result. T10 owns the single shared repair retry and final turn outcome; T5 makes no model calls, spends no retry and does not turn a citation failure into a failed specialist turn.

What went wrong / limits:

- Implementation tests and all named mutation checks passed; no surviving mutation required a new test.
- The user's section reference differed from the document numbering. The enumerated requirements agree with section 13 rule 4 and section 5, so no contract edit or clarification was needed.
- The contract does not define word tokenization in detail. This checker counts whitespace-separated units containing at least one letter or digit, after style normalization, summed across ellipsis parts. Hyphenated words count as one; standalone punctuation and ellipses do not count. This convention is documented in the function and tested at both boundaries and across skips.
- A successful match proves that quoted text occurs in a source shown in that turn. It does not prove that the source supports the claim or that the claim is clinically correct.
- All examples are synthetic, with no provider calls, dependency installs or network access. General trace integration and repair orchestration belong to later tasks. No T6 work was started.
- Existing architecture Markdown/SVG/PNG edits were preserved. Mutation checks used an isolated committed worktree, with the main virtual-environment interpreter and pytest's src path, to keep every restore/status check clean without hiding the human's changes.

#### T5 contract check

All test names below refer to `tests/test_grounding.py`.

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 13 rule 4: exact copied words match | `quote_failure` | `test_exact_match` |
| Case differences ignored | `normalize_quote_text` | `test_case_difference` |
| Extra whitespace ignored | `normalize_quote_text` | `test_extra_whitespace` |
| Curly and straight quote styles equivalent | `normalize_quote_text` | `test_curly_vs_straight_quotes` |
| Em dash and hyphen styles equivalent | `normalize_quote_text` | `test_em_dash_vs_hyphen` |
| Literal three-dot skips, parts in order | `quote_failure` | `test_ellipsis_parts_in_order` |
| Out-of-order parts rejected | forward search cursor in `quote_failure` | `test_ellipsis_parts_out_of_order_fail` |
| Under four words rejected | total word count in `quote_failure` | `test_under_four_words_fails` |
| Over forty words rejected | total word count in `quote_failure` | `test_over_forty_words_fails` |
| Inclusive four/forty boundaries; total across parts | `quote_failure` | `test_four_word_boundary_passes`, `test_forty_word_boundary_passes`, `test_ellipsis_word_count_is_total_and_excludes_skip_marker` |
| Section 13 rule 3: source actually shown in that turn | `verify_citation` shown_ids check | `test_passage_not_shown_this_turn_fails`, `test_case_source_must_also_be_shown` |
| Section 13 rule 3: cited ID exists | `verify_citation` registry membership | `test_unknown_passage_id_fails` (even when listed in shown IDs) |
| Changed word rejected | literal match and word boundaries | `test_one_changed_word_fails`, `test_substring_at_word_boundaries_is_not_a_quote` |
| Ordered parts cannot reuse overlapping source words | cursor advances to match end | `test_ellipsis_cannot_reuse_overlapping_words`, `test_later_occurrence_can_complete_ordered_match` |
| Match only the cited source, not another source or a union | source lookup by passage_id | `test_quote_is_checked_against_its_named_source`, `test_no_cross_source_stitching` |
| No unrequested fuzzy/regex matching | `re.escape` and literal punctuation | `test_literal_punctuation_not_regex_or_fuzzy_matching` |
| Citation.passage_id and quote | copied unchanged from draft | `test_citation_preserves_data_and_sets_code_owned_fields` |
| Citation.source_type | code derives case vs KB candidate from ID prefix | `test_exact_match`, `test_citation_preserves_data_and_sets_code_owned_fields` |
| Citation.verified | code combines existence, shown IDs and quote check | exact, unknown-ID, unshown-source and changed-word tests |
| Citation.verify_note | safe failure reason or empty on success | exact, unknown-ID, length and order tests; `test_failure_notes_do_not_echo_untrusted_data` |
| Claim.claim_id, text, citations | caller ID, unchanged draft text, newly checked citations | `test_claim_requires_every_citation_to_pass` |
| Claim.grounding_status; section 13 rule 2 | nonempty citation list and every citation verified | `test_claim_requires_citations`, `test_claim_requires_every_citation_to_pass`, `test_rechecking_repaired_claim_can_ground_it` |
| Section 4 / rule 3: Round 2 carryover must actually be shown again | current shown_ids, no automatic historic exemption | `test_round2_carryover_only_verifies_when_shown_again` |
| User: normalization in one function, used only for quote checks | `normalize_quote_text`; only two calls within `quote_failure` | quote-style tests plus repository reference search |

No T5 contract requirement is knowingly implemented differently from the written rule. Repair scheduling and final post-retry status integration remain T10, not an additional retry path in this module.

#### T5 mutation audit

Re-run from a clean checkout:

```powershell
.venv/Scripts/python.exe -m pytest -p no:cacheprovider
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/grounding.py --spec tools/t5_mutations.json
```

All 33 deliberate breaks were detected on committed code `3f6a64e` in `.venv/t5-audit`. Each ran the full suite, produced the named failing test, restored the file with `git restore`, and confirmed clean Git status before the next mutation. The table records the actual observed failures. Final restored-code tests: 838 passed.

| Rule | What was broken | Which test failed |
|---|---|---|
| Case normalization | `text.translate(styles).casefold() -> text.translate(styles)` | `tests/test_grounding.py::test_case_difference` |
| Whitespace normalization | `" ".join(text.translate(styles).casefold().split()) -> text.translate(styles).casefold()` | `tests/test_grounding.py::test_extra_whitespace` |
| Curly single quote | `"’": "'" -> "’": "’"` | `tests/test_grounding.py::test_curly_vs_straight_quotes` |
| Curly double quote | `"“": '"' -> "“": "“"` | `tests/test_grounding.py::test_curly_vs_straight_quotes` |
| Em dash and hyphen | `"—": "-" -> "—": "—"` | `tests/test_grounding.py::test_em_dash_vs_hyphen` |
| Split ellipsis into parts | `normalized.split("...") -> [normalized]` | `tests/test_grounding.py::test_ellipsis_parts_in_order` |
| Ellipsis parts in order | `cursor = match.end() -> cursor = 0` | `tests/test_grounding.py::test_ellipsis_parts_out_of_order_fail` |
| Ellipsis cannot overlap | `cursor = match.end() -> cursor = match.start()` | `tests/test_grounding.py::test_ellipsis_cannot_reuse_overlapping_words` |
| Under four words rejected | `if word_count < 4: -> if word_count < 3:` | `tests/test_grounding.py::test_under_four_words_fails` |
| Four words accepted | `if word_count < 4: -> if word_count < 5:` | `tests/test_grounding.py::test_four_word_boundary_passes` |
| Over forty words rejected | `if word_count > 40: -> if word_count > 41:` | `tests/test_grounding.py::test_over_forty_words_fails` |
| Forty words accepted | `if word_count > 40: -> if word_count > 39:` | `tests/test_grounding.py::test_forty_word_boundary_passes` |
| Total words excludes ellipsis | `word_count = sum(any(char.isalnum() for char in word) for part in parts for word in part.split()) -> word_count = len(normalized.split())` | `tests/test_grounding.py::test_ellipsis_word_count_is_total_and_excludes_skip_marker` |
| Parts must be found | `if match is None: /             return "quote text not found in source in order" -> if match is None: /             return None` | `tests/test_grounding.py::test_one_changed_word_fails` |
| Literal punctuation | `re.escape(part) -> part` | `tests/test_grounding.py::test_literal_punctuation_not_regex_or_fuzzy_matching` |
| Left word boundary | `left = r"(?<!\w)" if part[0].isalnum() or part[0] == "_" else "" -> left = ""` | `tests/test_grounding.py::test_substring_at_word_boundaries_is_not_a_quote` |
| Right word boundary | `right = r"(?!\w)" if part[-1].isalnum() or part[-1] == "_" else "" -> right = ""` | `tests/test_grounding.py::test_substring_at_word_boundaries_is_not_a_quote` |
| Known source registry required | `if draft.passage_id not in sources: -> if False:` | `tests/test_grounding.py::test_unknown_passage_id_fails` |
| Shown in this turn required | `elif draft.passage_id not in shown_ids: -> elif False:` | `tests/test_grounding.py::test_passage_not_shown_this_turn_fails` |
| Only named source may support quote | `sources[draft.passage_id] -> next(iter(sources.values()))` | `tests/test_grounding.py::test_quote_is_checked_against_its_named_source` |
| Preserve original quote | `passage_id=draft.passage_id, quote=draft.quote, -> passage_id=draft.passage_id, quote=draft.quote.strip(),` | `tests/test_grounding.py::test_citation_preserves_data_and_sets_code_owned_fields` |
| Preserve passage ID | `passage_id=draft.passage_id, quote=draft.quote, -> passage_id="wrong", quote=draft.quote,` | `tests/test_grounding.py::test_citation_preserves_data_and_sets_code_owned_fields` |
| Case source type | `source_type="case" if draft.passage_id.startswith("CASE-") else "kb" -> source_type="kb"` | `tests/test_grounding.py::test_exact_match` |
| KB source type | `source_type="case" if draft.passage_id.startswith("CASE-") else "kb" -> source_type="case"` | `tests/test_grounding.py::test_citation_preserves_data_and_sets_code_owned_fields` |
| Verified true for valid match | `verified=reason is None -> verified=False` | `tests/test_grounding.py::test_exact_match` |
| Verified false for failure | `verified=reason is None -> verified=True` | `tests/test_grounding.py::test_one_changed_word_fails` |
| Failure explanation | `verify_note=reason or "" -> verify_note=""` | `tests/test_grounding.py::test_unknown_passage_id_fails` |
| Failure notes do not echo input | `reason = "unknown passage ID" -> reason = "unknown passage ID: " + draft.passage_id` | `tests/test_grounding.py::test_failure_notes_do_not_echo_untrusted_data` |
| Claim needs at least one citation | `bool(citations) and all(citation.verified for citation in citations) -> all(citation.verified for citation in citations)` | `tests/test_grounding.py::test_claim_requires_citations` |
| All claim citations must verify | `all(citation.verified for citation in citations) -> any(citation.verified for citation in citations)` | `tests/test_grounding.py::test_claim_requires_every_citation_to_pass` |
| Claim code-owned status | `grounding_status="grounded" if grounded else "ungrounded" -> grounding_status="ungrounded"` | `tests/test_grounding.py::test_rechecking_repaired_claim_can_ground_it` |
| Claim ID from caller | `Claim(claim_id=claim_id, text=draft.text -> Claim(claim_id="wrong", text=draft.text` | `tests/test_grounding.py::test_claim_requires_every_citation_to_pass` |
| Preserve claim text | `Claim(claim_id=claim_id, text=draft.text -> Claim(claim_id=claim_id, text="wrong"` | `tests/test_grounding.py::test_claim_requires_every_citation_to_pass` |

Human review starting points:

1. `src/council/grounding.py` - `normalize_quote_text`: all permitted normalization in one place.
2. `src/council/grounding.py` - `quote_failure`: lengths, skips, ordering and literal matching.
3. `src/council/grounding.py` - `verify_citation`: source registry, turn availability and code-owned verification.


### T6: dissent and confidence

The human resolved the two gaps that initially stopped T6: skipped Round 2 uses Round 1 as final, and no working specialist means a bare report with no chair call. Stale working copies had also removed the privacy rules; work paused instead of committing those deletions. At the human's explicit instruction, restored only docs/design.md and docs/data-contracts.md from HEAD, verified each of the five supplied old texts occurred exactly once, applied their exact replacements, displayed the diff, and committed as 8135a2c (Docs: Round 2 skipped and all-specialists-failed cases). No earlier supplied file was used.

Implemented src/council/scoring.py, tests/test_scoring.py and tools/t6_mutations.json, committed as a1b910c before the mutation audit. The fixed stance table drives both dissent and agreement. Final argument selection uses a successful Round 2 argument, otherwise the successful Round 1 argument; failed Round 1 specialists stay excluded. Dissent copies the final role, stance, argument ID and chair note. The warning requires a strict majority of the non-failed specialists.

Confidence averages individual criterion scores from the latest judged round, uses the share of accepting specialists, applies the three capped penalties, clamps to 0–100 and assigns the exact 40/70 boundaries. Judge-round selection is global; claim and disagreement penalties select the final argument separately for each specialist. Rebuttal response claims are claims too; repeated claim IDs are counted once. Raw scores and turn records are expected to have passed their upstream ID/uniqueness checks. Existing contract models are used without new report shapes.

What went wrong / limits:

- One initial test fixture incorrectly expected 70 from arithmetic that yields 67.5. Corrected the synthetic inputs; the final full suite passes 892 tests (54 new T6 cases).
- No confidence value is manufactured for zero working specialists: final_arguments returns an empty list and compute_confidence returns None, with empty dissent and no warning. The later chair/report and orchestrator tasks (T14/T15) must use this signal to skip the chair and write the INCOMPLETE bare report with reason "all specialists failed". T6 does not implement model calls or report writing.
- Full scorecard aggregation, chair ID checks and report integration remain in their later tasks. No T7 work was started. No contract behavior was silently changed; no unresolved T6 contract deviation remains.
- Tests use synthetic records and arithmetic only, with no provider calls, network access or new dependencies. Existing architecture.md/png/svg edits were preserved. The mutation audit ran in an isolated checkout of the committed code using the main virtual environment; each break was undone with git restore and Git status verified clean before the next break.

#### T6 contract check

Implementations below are in src/council/scoring.py; tests are in tests/test_scoring.py.

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 1 specialist roles; section 5 Argument.role, round, status, stance, argument_id | final_arguments selects only four specialists, uses R2 or R1 fallback, excludes failed R1 | test_final_round_selection_and_failed_specialists, test_round2_failed_or_skipped_falls_back |
| Section 12 accepted stances, all four recommendations and three stances | ACCEPTED_STANCES, compute_dissent, compute_confidence | test_stance_table (12 combinations) |
| Section 8 dissent.role, stance, argument_id, note; role_notes copied exactly | compute_dissent | test_stance_table, test_round2_failed_or_skipped_falls_back |
| Sections 8/12 council_warning, strictly more than half of working specialists | council_warning | test_warning_requires_strict_majority |
| Section 8 bare-report confidence=null, dissent=[], council_warning=null when all specialists fail | final_arguments, compute_confidence, compute_dissent, council_warning; report creation and chair skip deferred to T14/T15 | test_no_working_final_argument_has_no_confidence |
| Sections 6/12 Score.round, groundedness, logic, uncertainty, counterarguments; null R1 criterion omitted; equal weight per criterion score across judges/arguments | judge_component | test_judge_round2_preferred_and_all_values_weighted_equally, test_judge_round1_fallback_even_when_round2_arguments_exist |
| Section 12 prefer judged R2, else R1, else judge_part=0 and judge_round_used=null | judge_component | same two judge-round tests, test_no_judges_and_failed_turns_lower_confidence |
| Sections 6/11/13 rule 18: Score.judge, argument_id, absolute gap >=2 per criterion, one judge means zero disagreements | disagreement_count | test_disagreements_absolute_per_criterion_and_one_judge_zero, test_disagreement_penalty_rate_and_cap |
| Sections 5/12 Claim.claim_id, grounding_status; Argument.claims and Rebuttal.response_claims; only final claims count | ungrounded_count, final_arguments | test_final_penalties_ignore_fixed_and_dropped_round1_claims, test_rebuttal_claims_count_once_by_id |
| Section 12 final round selected per specialist, including failed/skipped R2, independently of judged round | final_arguments, ungrounded_count, disagreement_count | test_round2_failed_or_skipped_falls_back, test_penalties_fall_back_per_role_not_per_judged_round |
| Sections 8/12 ConfidenceInputs.judge_part, judge_round_used, agreement_part, specialists_counted, specialists_accepting, base | compute_confidence, judge_component | test_no_judges_and_failed_turns_lower_confidence (all fields), test_stance_table, judge-round tests |
| Sections 8/12 ungrounded_claims.count and penalty: 5 each, cap 20 | compute_confidence | test_ungrounded_penalty_rate_and_cap |
| Sections 7/8/12 RedTeamFinding.severity; high_severity_findings.count and penalty: high only, 10 each, cap 20 | compute_confidence | test_high_findings_penalty_rate_and_cap |
| Sections 8/12 judge_disagreements.count and penalty: 5 each, cap 10 | compute_confidence, disagreement_count | test_disagreement_penalty_rate_and_cap |
| Sections 8/12 total_penalty and Confidence.score: base minus all penalties, clamp 0–100 | compute_confidence, clamp_score | test_combined_penalties_and_lower_clamping, test_clamping |
| Sections 8/12 Confidence.level and inputs: >=70 high, >=40 medium, otherwise low; no rounding before comparison | confidence_level, compute_confidence | test_level_boundaries, test_level_boundaries_through_formula, test_high_boundary_through_formula |
| Section 13 rule 9: dissent and confidence computed by code | compute_dissent, compute_confidence construct full existing models | test_stance_table and formula tests |
| Section 13 rules 16/17: failed R1 stays failed; failed turns excluded from final stance counts | final_arguments | test_final_round_selection_and_failed_specialists, test_no_working_final_argument_has_no_confidence |

#### T6 mutation audit

Re-run from a clean checkout with the project virtual environment:

```powershell
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/scoring.py --spec tools/t6_mutations.json
```

The existing runner executes the full suite for each mutation, requires the named test to fail, restores the committed target with git restore, and requires a clean, fully readable Git status. Use --list to preview without edits. No new tests were needed after the initial implementation commit.

| Rule | What was broken | Test that failed |
|---|---|---|
| Proceed accepts for only | `Recommendation.PROCEED: frozenset({Stance.FOR}) -> Recommendation.PROCEED: frozenset({Stance.FOR, Stance.CONDITIONAL})` | `tests/test_scoring.py::test_stance_table` |
| Modifications accepts conditional | `Recommendation.PROCEED_WITH_MODIFICATIONS: frozenset({Stance.FOR, Stance.CONDITIONAL}) -> Recommendation.PROCEED_WITH_MODIFICATIONS: frozenset({Stance.FOR})` | `tests/test_scoring.py::test_stance_table` |
| Delay accepts against | `Recommendation.DELAY_PENDING_INVESTIGATION: frozenset({Stance.CONDITIONAL, Stance.AGAINST}) -> Recommendation.DELAY_PENDING_INVESTIGATION: frozenset({Stance.CONDITIONAL})` | `tests/test_scoring.py::test_stance_table` |
| Decline accepts against only | `Recommendation.DECLINE: frozenset({Stance.AGAINST}) -> Recommendation.DECLINE: frozenset({Stance.AGAINST, Stance.FOR})` | `tests/test_scoring.py::test_stance_table` |
| Count specialists only | `(Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN) -> (Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN, Role.CHAIR)` | `tests/test_scoring.py::test_final_round_selection_and_failed_specialists` |
| Failed Round 1 stays failed | `first is None or first.status == TurnStatus.FAILED -> first is None` | `tests/test_scoring.py::test_final_round_selection_and_failed_specialists` |
| Successful Round 2 supersedes Round 1 | `final.append(second if second is not None and second.status == TurnStatus.OK else first) -> final.append(first)` | `tests/test_scoring.py::test_final_round_selection_and_failed_specialists` |
| Failed Round 2 uses Round 1 | `second is not None and second.status == TurnStatus.OK -> second is not None` | `tests/test_scoring.py::test_round2_failed_or_skipped_falls_back` |
| Skipped Round 2 uses Round 1 | `second = turns.get((role, 2)) -> second = turns.get((role, 2)) /         if second is None: /             continue` | `tests/test_scoring.py::test_round2_failed_or_skipped_falls_back` |
| Dissent note copied exactly | `note=role_notes[argument.role] -> note="Changed note"` | `tests/test_scoring.py::test_stance_table` |
| Dissent carries final argument ID | `argument_id=argument.argument_id, note= -> argument_id="R1-ADMIN", note=` | `tests/test_scoring.py::test_stance_table` |
| Only unaccepted positions dissent | `if argument.stance not in ACCEPTED_STANCES[recommendation] -> if argument.stance in ACCEPTED_STANCES[recommendation]` | `tests/test_scoring.py::test_stance_table` |
| Warning requires more than half | `if dissenters > len(final) / 2: -> if dissenters >= len(final) / 2:` | `tests/test_scoring.py::test_warning_requires_strict_majority` |
| Warning denominator excludes failed specialists | `if dissenters > len(final) / 2: -> if dissenters > 4 / 2:` | `tests/test_scoring.py::test_warning_requires_strict_majority` |
| Prefer latest judged round | `for round_number in (2, 1): -> for round_number in (1, 2):` | `tests/test_scoring.py::test_judge_round2_preferred_and_all_values_weighted_equally` |
| Round 1 scores remain fallback | `for round_number in (2, 1): -> for round_number in (2,):` | `tests/test_scoring.py::test_judge_round1_fallback_even_when_round2_arguments_exist` |
| Average all judges arguments and criteria | `mean(values) - 1 -> mean(values[:4]) - 1` | `tests/test_scoring.py::test_judge_round2_preferred_and_all_values_weighted_equally` |
| Exclude null Round 1 counterarguments | `if (value := getattr(score, criterion.value)) is not None -> if (value := (getattr(score, criterion.value) or 0)) is not None` | `tests/test_scoring.py::test_judge_round1_fallback_even_when_round2_arguments_exist` |
| Judge scale subtracts one | `(mean(values) - 1) / 4 * 100 -> mean(values) / 4 * 100` | `tests/test_scoring.py::test_judge_round1_fallback_even_when_round2_arguments_exist` |
| Judge scale divides by four | `(mean(values) - 1) / 4 * 100 -> (mean(values) - 1) / 5 * 100` | `tests/test_scoring.py::test_judge_round1_fallback_even_when_round2_arguments_exist` |
| No scores means zero and null round | `return 0.0, None -> return 100.0, 1` | `tests/test_scoring.py::test_no_judges_and_failed_turns_lower_confidence` |
| Only final arguments incur disagreements | `if score.argument_id == argument.argument_id -> if score.argument_id.endswith(argument.role.value)` | `tests/test_scoring.py::test_final_penalties_ignore_fixed_and_dropped_round1_claims` |
| One judge has zero disagreements | `if len(judges) != 2: /             continue -> if len(judges) != 2: /             count += 1 /             continue` | `tests/test_scoring.py::test_disagreements_absolute_per_criterion_and_one_judge_zero` |
| Disagreement gap includes two | `abs(left - right) >= 2 -> abs(left - right) > 2` | `tests/test_scoring.py::test_disagreements_absolute_per_criterion_and_one_judge_zero` |
| Disagreement gap is absolute | `abs(left - right) >= 2 -> (left - right) >= 2` | `tests/test_scoring.py::test_disagreements_absolute_per_criterion_and_one_judge_zero` |
| Rebuttal claims also counted | `if argument.rebuttal is not None: -> if False:` | `tests/test_scoring.py::test_rebuttal_claims_count_once_by_id` |
| Only code-ungrounded claims penalized | `claim.grounding_status == GroundingStatus.UNGROUNDED -> True` | `tests/test_scoring.py::test_final_penalties_ignore_fixed_and_dropped_round1_claims` |
| Final claims only, per role fallback | `ungrounded = ungrounded_count(final) -> ungrounded = ungrounded_count(arguments)` | `tests/test_scoring.py::test_penalties_fall_back_per_role_not_per_judged_round` |
| All specialists failed means null confidence | `if not final: /         return None -> if False: /         return None` | `tests/test_scoring.py::test_no_working_final_argument_has_no_confidence` |
| Agreement uses nonfailed denominator | `agreement_part = accepting / len(final) * 100 -> agreement_part = accepting / 4 * 100` | `tests/test_scoring.py::test_no_judges_and_failed_turns_lower_confidence` |
| Base gives equal weight to judges and agreement | `base = 0.5 * judge_part + 0.5 * agreement_part -> base = 0.6 * judge_part + 0.4 * agreement_part` | `tests/test_scoring.py::test_no_judges_and_failed_turns_lower_confidence` |
| Only high findings penalized | `finding.severity == Level.HIGH -> finding.severity != Level.LOW` | `tests/test_scoring.py::test_high_findings_penalty_rate_and_cap` |
| Ungrounded rate | `5 * ungrounded -> 4 * ungrounded` | `tests/test_scoring.py::test_ungrounded_penalty_rate_and_cap` |
| Ungrounded cap | `min(20, 5 * ungrounded) -> min(25, 5 * ungrounded)` | `tests/test_scoring.py::test_ungrounded_penalty_rate_and_cap` |
| Finding rate | `10 * high -> 5 * high` | `tests/test_scoring.py::test_high_findings_penalty_rate_and_cap` |
| Finding cap | `min(20, 10 * high) -> min(30, 10 * high)` | `tests/test_scoring.py::test_high_findings_penalty_rate_and_cap` |
| Disagreement rate | `5 * disagreements -> 4 * disagreements` | `tests/test_scoring.py::test_disagreement_penalty_rate_and_cap` |
| Disagreement cap | `min(10, 5 * disagreements) -> min(15, 5 * disagreements)` | `tests/test_scoring.py::test_disagreement_penalty_rate_and_cap` |
| Sum all penalties | `ungrounded_penalty.penalty + high_penalty.penalty + disagreement_penalty.penalty -> ungrounded_penalty.penalty + high_penalty.penalty` | `tests/test_scoring.py::test_combined_penalties_and_lower_clamping` |
| Subtract penalties | `clamp_score(base - total) -> clamp_score(base + total)` | `tests/test_scoring.py::test_combined_penalties_and_lower_clamping` |
| Clamp below zero | `max(0.0, score) -> score` | `tests/test_scoring.py::test_clamping` |
| Clamp above 100 | `min(100.0, max(0.0, score)) -> max(0.0, score)` | `tests/test_scoring.py::test_clamping` |
| High includes 70 | `if score >= 70: -> if score > 70:` | `tests/test_scoring.py::test_level_boundaries` |
| Medium includes 40 | `if score >= 40: -> if score > 40:` | `tests/test_scoring.py::test_level_boundaries` |
| Count repeated claim IDs only once | `claims.update((claim.claim_id, claim) for claim in argument.rebuttal.response_claims) -> claims.update((claim.claim_id + "-duplicate", claim) for claim in argument.rebuttal.response_claims)` | `tests/test_scoring.py::test_rebuttal_claims_count_once_by_id` |


All 45 mutations were detected by their named tests. Committed code was restored and the audit worktree was clean after every mutation.

### T7: budget and trace

`src/council/budget.py`, `src/council/trace.py`, `tests/test_budget.py`, `tests/test_trace.py` and the `tests/conftest.py` `--race-iterations` option were already present, untracked, at the start of this session, along with draft mutation specs in `tools/t7_budget_mutations.json` and `tools/t7_trace_mutations.json`. Nothing had been committed, tested against the contracts, mutation-checked or logged, so this was treated as an unreviewed pull request rather than finished work.

Review against `data-contracts.md` section 11 (Budget and config) and section 10 (Trace event), plus section 13 rules 10 and 12: `Budget` holds `BudgetState` (`tokens_used`, `calls_used`, `started_at`, `exhausted`, `reason`) behind one `Lock`, takes a conservative reservation (input tokens plus the role's output cap) at admission time and settles actual usage once, so concurrent attempts cannot spend the same remaining room twice. Only `Role.CHAIR` is exempt from `chair_reserve` (tokens, calls, seconds); every other role is capped at the maximum minus the reserve, and only the chair can still be admitted once the non-chair ceiling is exhausted. `TraceWriter` creates the trace file exclusively (never overwrites a prior run's trace), overwrites `run_id`, `seq` and `timestamp` on every event under its own `Lock`, and stops permanently after any write failure rather than silently losing events. Both locks were exercised together in `test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps` (32 threads interleaving admission, settlement and trace writes) with no lost tokens and no sequence gaps.

What went wrong / limits:

- No contract or code defect was found in the draft; the review changed nothing in `budget.py` or `trace.py`.
- The mutation tool (`tools/mutation_check.py`) refuses to run against a dirty working tree and restores the target file with `git restore`, which only works on tracked files. The draft's own code, tests and mutation specs were all untracked, so nothing could be audited until it was committed. Followed the T6 precedent: committed the code and tests first (`T7: budget and trace with tests`), then the mutation spec JSON files (`T7: mutation audit specs for budget and trace`), then ran the audit.
- The reservation system (holding pending input+output tokens between admission and settlement) and the "never overwrite an existing trace file" rule are not literally specified in the contracts; they are sound implementation choices for the concurrency guarantee the task requires (no lost tokens, no sequence gaps under many parallel threads) and do not conflict with anything in `design.md` or `data-contracts.md`.
- T7 implements accounting and the audit log only; it does not call the gateway's privacy check, API retry or model dispatch, which are T8's scope.

#### T7 contract check

Implementations are in `src/council/budget.py` and `src/council/trace.py`; tests are in `tests/test_budget.py` and `tests/test_trace.py`.

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 11 BudgetState: tokens_used, calls_used, started_at, exhausted, reason | `Budget.__init__`, `Budget.snapshot` | test_initial_state_config_and_snapshot_are_isolated |
| Section 11 max_tokens_per_call per role (specialist/judge/red_team/chair) | `Budget.output_cap`, enforced in `check_and_reserve` | test_role_output_caps |
| Section 11 max_total_tokens, max_calls, max_seconds_total | `check_and_reserve` token/call/time limits | test_pending_reservations_prevent_oversubscription, test_call_limit_counts_every_attempt_even_zero_usage_failures, test_time_limits_and_chair_reserve_use_elapsed_time |
| Section 11 chair_reserve (tokens, calls, seconds); design.md "only the chair can spend it, others stop at max minus reserve" | `check_and_reserve` reserve subtraction gated on `role == Role.CHAIR` | test_only_chair_can_spend_token_reserve, test_call_limit_counts_every_attempt_even_zero_usage_failures, test_time_limits_and_chair_reserve_use_elapsed_time |
| Section 13 rule 10: budget checked before every call; refuse when exhausted | `check_and_reserve` raises `BudgetExhausted` and records `exhausted`/`reason` | test_exhaustion_stays_visible_and_stops_other_roles |
| Section 13 rule 12 / section 11: budget counter and trace seq guarded by a lock | `Budget._lock`, `TraceWriter._lock` | test_budget_operations_wait_for_shared_lock, test_trace_write_waits_for_shared_lock, test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Section 10 TraceEvent: run_id, seq, timestamp assigned by the writer, not the caller | `TraceWriter.write` overwrites these three fields | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| Section 10 "seq is assigned under a lock"; gapless, increasing across threads | `TraceWriter.write` seq increment inside `_lock` | test_trace_jsonl_preserves_fields_and_owns_order_and_time, test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Section 14 trace.jsonl: one append-only file per run | `TraceWriter.__init__` opens with `xb` (exclusive create), writes append with `ab` | test_existing_trace_is_never_overwritten |
| Tasks.md T7: "Trace lines get unique, increasing seq under many parallel threads" | Combined budget+trace race test, 32 threads | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps (re-run at 300 iterations/thread = 9600 calls during this review, beyond the default 25) |

#### T7 mutation audit

Re-run from a clean checkout with the project virtual environment, after committing the code, tests and mutation specs:

```powershell
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/budget.py --spec tools/t7_budget_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/trace.py --spec tools/t7_trace_mutations.json
```

**budget.py (33 mutations)**

| Rule | What was broken | Test that failed |
|---|---|---|
| Private config snapshot | `self._config = config.model_copy(deep=True)` -> `self._config = config` | test_initial_state_config_and_snapshot_are_isolated |
| Detached state snapshot | `return self._state.model_copy(deep=True)` -> `return self._state` | test_initial_state_config_and_snapshot_are_isolated |
| Snapshot guarded by shared lock | `with self._lock:` (snapshot) -> `nullcontext()` | test_budget_operations_wait_for_shared_lock |
| Admission guarded by shared lock | `with self._lock:` (check_and_reserve) -> `nullcontext()` | test_budget_operations_wait_for_shared_lock |
| Settlement guarded by shared lock | `with self._lock:` (complete) -> `nullcontext()` | test_budget_operations_wait_for_shared_lock |
| Identity-based reservation ownership | `@dataclass(frozen=True, eq=False)` -> `@dataclass(frozen=True)` | test_settlement_rejects_unknown_duplicate_and_over_bound_usage |
| Nonnegative integer accounting | `type(value) is not int or value < 0` -> `False` | test_invalid_token_counts_never_change_state |
| Output cap specialist | `max_tokens_per_call.specialist` -> `+ 1` | test_role_output_caps |
| Output cap judge | `max_tokens_per_call.judge` -> `+ 1` | test_role_output_caps |
| Output cap red_team | `max_tokens_per_call.red_team` -> `+ 1` | test_role_output_caps |
| Output cap chair | `max_tokens_per_call.chair` -> `+ 1` | test_role_output_caps |
| Requested output respects cap | `if output > cap:` -> `if False:` | test_role_output_caps |
| Only chair spends reserve | `chair = role == Role.CHAIR` -> `chair = True` | test_only_chair_can_spend_token_reserve |
| Exhaustion stops non-chair attempts | `if self._state.exhausted and not chair:` -> `if False:` | test_exhaustion_stays_visible_and_stops_other_roles |
| Token reserve withheld | `(0 if chair else chair_reserve.tokens)` -> `0` | test_only_chair_can_spend_token_reserve |
| Call reserve withheld | `(0 if chair else chair_reserve.calls)` -> `0` | test_call_limit_counts_every_attempt_even_zero_usage_failures |
| Time reserve withheld | `(0 if chair else chair_reserve.seconds)` -> `0` | test_time_limits_and_chair_reserve_use_elapsed_time |
| Elapsed time measured from start | `(clock() - started_at)` -> `clock()` | test_time_limits_and_chair_reserve_use_elapsed_time |
| Input tokens reserved | `total = tokens_in + output` -> `total = output` | test_pending_reservations_prevent_oversubscription |
| Output tokens reserved | `total = tokens_in + output` -> `total = tokens_in` | test_pending_reservations_prevent_oversubscription |
| Pending tokens count against limit | `sum(self._pending.values())` -> `0` | test_pending_reservations_prevent_oversubscription |
| Exact token limit is usable | `+ total > token_limit:` -> `>= token_limit:` | test_only_chair_can_spend_token_reserve |
| Call cap cannot be exceeded | `calls_used >= call_limit` -> `> call_limit` | test_call_limit_counts_every_attempt_even_zero_usage_failures |
| Time deadline rejects at boundary | `elif remaining <= 0:` -> `< 0:` | test_time_limits_and_chair_reserve_use_elapsed_time |
| Exhausted flag recorded | `self._state.exhausted = True` -> `False` | test_pending_reservations_prevent_oversubscription |
| Exhaustion reason recorded | `self._state.reason = reason` -> `None` | test_pending_reservations_prevent_oversubscription |
| Every admitted attempt counted once | `calls_used += 1` -> `+= 2` | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Actual input bound checked | drop the `tokens_in > reservation.tokens_in` half | test_settlement_rejects_unknown_duplicate_and_over_bound_usage |
| Actual output bound checked | drop the `tokens_out > reservation.max_tokens_out` half | test_settlement_rejects_unknown_duplicate_and_over_bound_usage |
| Actual input tokens counted | `tokens_used += tokens_in + tokens_out` -> `+= tokens_out` | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Actual output tokens counted | `tokens_used += tokens_in + tokens_out` -> `+= tokens_in` | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Settlement releases reservation exactly once | `del self._pending[reservation]` -> `pass` | test_parallel_same_reservation_is_settled_once |
| Returned settlement snapshot cannot alter budget | `return self._state.model_copy(deep=True)` -> `return self._state` | test_settlement_releases_unused_room_and_counts_both_token_directions |

**trace.py (11 mutations)**

| Rule | What was broken | Test that failed |
|---|---|---|
| Existing trace never overwritten | `self._path.open("xb")` -> `"wb"` | test_existing_trace_is_never_overwritten |
| Sequence and write share a lock | `with self._lock:` -> `nullcontext()` | test_trace_write_waits_for_shared_lock |
| Writer owns run ID | `run_id=self._run_id` -> `run_id=event.run_id` | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| Gapless incrementing sequence | `seq=self._seq + 1` -> `+ 2` | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |
| Writer owns timestamp | `timestamp=datetime.now(...)` -> `timestamp=event.timestamp` | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| Full event data preserved | inject `data["raw_output"] = None` | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| JSON lines separated | drop the trailing `"\n"` | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| Append never truncates existing events | `self._path.open("ab")` -> `"wb"` | test_trace_jsonl_preserves_fields_and_owns_order_and_time |
| Short write treated as failure | `if written != len(payload):` -> `if False:` | test_short_write_stops_writer |
| Failed writer remains stopped | `self._failed = True` -> `False` | test_write_failure_is_explicit_and_writer_stops |
| Advance sequence after successful write | `self._seq = recorded.seq` -> `= 0` | test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps |

All 44 mutations were detected by their named tests. Committed code was restored and the audit worktree was clean after every mutation.

### T8: gateway and fake provider

`LLMGateway.call()` is the one path from agent code to a model. Per call it: runs the privacy check (contracts rule 20 — provider must be in `privacy.approved_providers`, and the prompt must match none of `privacy.py`'s shared `IDENTIFIER_PATTERNS` via `scan_identifiers`, reused rather than duplicated); then loops over up to `retries.max_api_attempts` (2) attempts, each one reserving budget room through `Budget.check_and_reserve` before calling the provider, retrying only `ProviderTimeout`/`ProviderRateLimit` with a configured wait, and writing exactly one `TraceEvent` per attempt (plus one `privacy_block` or `budget` event for a refusal, before any attempt is made, with `prompt` left null so nothing sent is ever recorded for a call that never went out). `model_choice_for`/`temperature_for` select the model and temperature per role from config (specialists share one model, judges another, matching design.md). Bad JSON is returned as plain text, untouched — parsing and repair remain later tasks' job.

`providers/base.py` defines `Provider` (one `complete` method) and `ProviderError`/`ProviderTimeout`/`ProviderRateLimit`; `providers/fake.py`'s `FakeProvider` replays a fixed script of `Scripted` outcomes or exception types, one per call, under its own lock, so a test can drive an exact sequence (good output, bad JSON text, a timeout, a rate limit) without a real model or network call.

What went wrong / limits:

- The first `estimate_tokens_in` used `len(prompt) // 4` chars-per-token, a plausible average but not a bound: a real successful call reporting `tokens_in` above that estimate made `Budget.complete` raise (`"actual usage exceeds the reserved bounds"`), since T7's `Budget.complete` requires settled usage to fall inside the reservation. Switched to `len(prompt)` itself: since no realistic tokenizer produces more tokens than there are characters in its input, that is a genuine upper bound, not just a typical one. The reservation over-reserves briefly; `Budget.complete` releases the unused room once real usage is known, so nothing is wasted long-term.
- The first tiny-budget mutation test (rule: "the reservation uses the token estimate, not a hardcoded value") survived its own mutation check: the budget's output cap alone already exceeded its limit (because of the chair-reserve subtraction), so forcing `tokens_in = 0` didn't change the outcome. Added `test_reservation_accounts_for_prompt_length_not_just_the_output_cap`, with a budget sized so the cap fits by itself but not with a 10-character prompt added, then re-pointed the mutation spec at it and re-ran the full audit (all 24 gateway mutations killed).
- Retrying only `ProviderTimeout` would have missed design.md's explicit "Retry API errors (timeouts, rate limits)" wording, so added `ProviderRateLimit` as a second retryable subtype of `ProviderError` and a `RETRYABLE_ERRORS` tuple, with its own test (`test_rate_limit_retries_once_then_succeeds`).
- The API-key test (`test_api_keys_never_appear_in_trace_or_run_bundle`) is necessarily a stand-in: no real provider adapter exists yet (that's T17, after live keys exist), so it uses a test-only `KeyHoldingProvider` that holds a fake key from an env var the way a real T17 adapter will, and asserts the key never appears in the written trace file or in a `{config_snapshot, trace_events}` bundle shaped like the relevant parts of `run.json` (which itself isn't assembled until T14/T15). This pins the invariant now; it cannot prove a not-yet-written real adapter will honor it, only that nothing in the gateway/trace path does anything with a key it is handed.
- Repair retries (separate from API retries, contracts section 13 rule 1) are not implemented here; `call()` accepts and records a `repair` flag on the trace event, but driving the one-repair-per-turn loop is T10's job, layered on top of the gateway.
- No real provider SDK is installed or imported anywhere (AGENTS.md: no network, minimum dependencies); `providers/base.py`/`fake.py` are the only files in the package today, and the import-graph test (`test_no_module_outside_providers_imports_a_provider_sdk`) enforces that anything beyond the stdlib and the project's declared dependencies (`pydantic`, `yaml`, `rank_bm25`) stays inside `providers/`, so a future real adapter cannot leak its SDK import elsewhere without failing this test.

#### T8 contract check

Implementations are in `src/council/gateway.py` and `src/council/providers/`; tests are in `tests/test_gateway.py` and `tests/test_providers.py`.

| Rule or field touched | Implementation | Test |
|---|---|---|
| design.md gateway step 1 / contracts rule 20: privacy checked before the budget check | `LLMGateway.call` calls `_refuse_if_privacy_blocked` before the budget/attempt loop | test_privacy_check_runs_before_the_budget_check |
| Contracts rule 20: provider must be in `privacy.approved_providers` | `_refuse_if_privacy_blocked` | test_privacy_blocks_unapproved_provider_before_any_attempt |
| Contracts rule 20: prompt must match no identifier pattern (shared list, not duplicated) | `_refuse_if_privacy_blocked` calls `council.privacy.scan_identifiers` | test_privacy_blocks_prompt_matching_identifier_pattern_without_leaking_it |
| Contracts rule 20 / design.md: a hit writes one `privacy_block` event with the kind only, never the value or the prompt | `_refuse_if_privacy_blocked` trace write: `error=reason` (kind text only), `prompt=None` | test_privacy_blocks_prompt_matching_identifier_pattern_without_leaking_it |
| Contracts rule 10 / design.md gateway step 2: budget checked before every call, refused when exhausted | `_reserve_or_refuse` via `Budget.check_and_reserve` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event, test_reservation_accounts_for_prompt_length_not_just_the_output_cap |
| A budget refusal also writes one event and never records the prompt | `_reserve_or_refuse` trace write, `event_type=EventType.BUDGET`, `prompt=None` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event |
| design.md gateway step 3: model picked per role from config, judges on a different model from specialists | `model_choice_for` | test_model_choice_for_maps_each_role_to_its_own_config_field, test_role_selects_configured_model_and_temperature |
| Section 11 `temperature`: per-role value, used only if the model allows it | `temperature_for` | test_temperature_for_maps_each_role_to_its_own_config_field |
| Section 11 `retries.max_api_attempts` (2); design.md: retry timeouts and rate limits with a short wait | `call()`'s attempt loop, `RETRYABLE_ERRORS`, `self._sleep(retries.api_retry_wait_seconds)` | test_timeout_retries_once_then_succeeds, test_rate_limit_retries_once_then_succeeds, test_timeout_twice_exhausts_attempts_and_refuses, test_non_timeout_provider_error_does_not_retry |
| design.md: "A retry ... is a new call through the gateway. It counts against the budget and appears in the trace." | reservation acquired inside the loop, once per attempt; one `TraceEvent` per attempt | test_every_attempt_counts_against_the_budget, test_timeout_retries_once_then_succeeds |
| Section 10 TraceEvent: prompt, raw_output, model, tokens_in/out, latency_ms, attempt, repair, budget_tokens_used, error | `call()`'s success/error trace writes | test_successful_call_returns_output_and_writes_one_llm_call_event |
| Section 10 `attempt: Literal[1, 2]` | loop bounded by `retries.max_api_attempts` (fixed at 2 by T2's config validation) | test_timeout_twice_exhausts_attempts_and_refuses |
| design.md: "Bad JSON is not the gateway's job." | `call()` returns `response.raw_output` unparsed on success | test_bad_json_output_is_returned_as_is_grounding_is_not_gateways_job |
| Section 11: "Agents never call a provider directly. There is no other path to a model." / tasks.md T8: a test fails if any module outside `providers/` imports a provider SDK | `providers/` package boundary; `LLMGateway` is the only caller of `Provider.complete` | test_no_module_outside_providers_imports_a_provider_sdk |
| Contracts rule 21: API keys never appear in `trace.jsonl` or `run.json` | gateway/trace path never reads or forwards environment values; test-only `KeyHoldingProvider` stands in for a future real adapter | test_api_keys_never_appear_in_trace_or_run_bundle |
| design.md: "One unit test: with a tiny budget, the call is refused." | `Budget.check_and_reserve` raising `BudgetExhausted`, converted to `GatewayRefusal` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event |
| tasks.md T8: `FakeProvider` supports scripted responses (good output, bad JSON, a timeout) so later tasks can drive specific scenarios | `providers/fake.py` `Scripted` / exception-type script entries | tests/test_providers.py (good output, bad JSON, timeout, rate limit, script order, exhaustion, cap enforcement) |

#### T8 mutation audit

Re-run from a clean checkout with the project virtual environment, after committing the code, tests and mutation specs:

```powershell
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/gateway.py --spec tools/t8_gateway_mutations.json
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/providers/fake.py --spec tools/t8_providers_mutations.json
```

**gateway.py (24 mutations)**

| Rule | What was broken | Test that failed |
|---|---|---|
| Provider approval checked before any attempt | `if provider not in ... approved_providers:` -> `if False:` | test_privacy_blocks_unapproved_provider_before_any_attempt |
| Identifier scan actually runs on the prompt | `hits = scan_identifiers(prompt)` -> `hits = []` | test_privacy_blocks_prompt_matching_identifier_pattern_without_leaking_it |
| Privacy block never records the prompt | `prompt=None` (privacy block) -> `prompt=prompt` | test_privacy_blocks_prompt_matching_identifier_pattern_without_leaking_it |
| Privacy refusal is actually raised | `raise GatewayRefusal(reason)` -> `pass` | test_privacy_blocks_unapproved_provider_before_any_attempt |
| Budget exhaustion is caught and converted to a refusal | `except BudgetExhausted as error:` -> `except TypeError as error:` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event |
| Budget refusal never records the prompt | `prompt=None` (budget refusal) -> `prompt="leaked"` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event |
| Budget refusal is actually raised | `raise GatewayRefusal(str(error)) from error` -> `pass` | test_tiny_budget_refuses_the_call_and_writes_one_budget_event |
| Retry is limited to retryable error types | `isinstance(error, RETRYABLE_ERRORS)` -> `True` | test_non_timeout_provider_error_does_not_retry |
| A retryable error actually retries instead of refusing immediately | drop the `continue` after `self._sleep(...)` | test_timeout_retries_once_then_succeeds |
| Settlement uses the actual response tokens, not zero | `budget.complete(reservation, response.tokens_in, response.tokens_out)` -> `(reservation, 0, 0)` | test_successful_call_returns_output_and_writes_one_llm_call_event |
| Successful trace event records the actual tokens_in | `tokens_in=response.tokens_in` -> `tokens_in=0` | test_successful_call_returns_output_and_writes_one_llm_call_event |
| Successful trace event records the actual tokens_out | `tokens_out=response.tokens_out` -> `tokens_out=0` | test_successful_call_returns_output_and_writes_one_llm_call_event |
| GatewayResult carries the provider's actual latency | `GatewayResult(..., latency_ms)` -> `GatewayResult(..., 0)` | test_successful_call_returns_output_and_writes_one_llm_call_event |
| Model choice: specialist roles use models.specialist | `return config.models.specialist` -> `return config.models.chair` | test_model_choice_for_maps_each_role_to_its_own_config_field |
| Model choice: chair uses models.chair | `return config.models.chair` -> `return config.models.red_team` | test_model_choice_for_maps_each_role_to_its_own_config_field |
| Model choice: red team uses models.red_team | `return config.models.red_team` -> `return config.models.chair` | test_model_choice_for_maps_each_role_to_its_own_config_field |
| Model choice: judge A and judge B are not interchangeable | swap the `judge_a`/`judge_b` branches | test_model_choice_for_maps_each_role_to_its_own_config_field |
| Temperature: specialist roles use temperature.specialist | `return config.temperature.specialist` -> `return config.temperature.chair` | test_temperature_for_maps_each_role_to_its_own_config_field |
| Temperature: judges use temperature.judge | `return config.temperature.judge` -> `return config.temperature.red_team` | test_temperature_for_maps_each_role_to_its_own_config_field |
| Temperature: red team uses temperature.red_team | `return config.temperature.red_team` -> `return config.temperature.judge` | test_temperature_for_maps_each_role_to_its_own_config_field |
| Temperature: chair uses temperature.chair | `return config.temperature.chair` -> `return config.temperature.specialist` | test_temperature_for_maps_each_role_to_its_own_config_field |
| Construction requires a registered provider for every configured role | `if choice["provider"] not in providers:` -> `if False:` | test_gateway_construction_requires_a_provider_for_every_configured_role |
| The role's budget output cap sizes the provider call, not an arbitrary value | `cap = self._budget.output_cap(role)` -> `cap = 1` | test_successful_call_returns_output_and_writes_one_llm_call_event |
| The reservation uses the token estimate, not a hardcoded value | `tokens_in = estimate_tokens_in(prompt)` -> `tokens_in = 0` | test_reservation_accounts_for_prompt_length_not_just_the_output_cap |

**providers/fake.py (6 mutations)**

| Rule | What was broken | Test that failed |
|---|---|---|
| Script advances one outcome per call | drop `self._index += 1` | test_script_replays_in_order_one_outcome_per_call |
| Script exhaustion raises ProviderError | `if self._index >= len(self._script):` -> `if False:` | test_script_exhaustion_raises_provider_error |
| Reserved output cap is enforced | `if outcome.tokens_out > max_tokens:` -> `if False:` | test_output_exceeding_the_reserved_cap_is_a_provider_error |
| A scripted exception type is actually raised | `if isinstance(outcome, type) and issubclass(...)` -> `if False:` | test_scripted_timeout_is_raised |
| An empty script is rejected at construction | `if not script:` -> `if False:` | test_empty_script_is_rejected_at_construction |
| calls_made reflects the real call count | `return self._index` -> `return 0` | test_script_replays_in_order_one_outcome_per_call |

All 30 mutations were detected by their named tests. Committed code was restored and the audit worktree was clean after every mutation.

### T1 addendum: PrivacySummary (contract gap found at Checkpoint A)

`docs/checkpoint-a.md` item 6 flagged that `docs/data-contracts.md` and `docs/design.md` had been edited after T1's models were committed, and asked for a check that `src/council/models.py` still matches. Walking every commit that touched either doc since T1 (`56b3d1d`, `4f4db15`, `a51aabf`, `8135a2c`, `7ddcec3`) found one real gap: `4f4db15` ("Docs: privacy barriers") added `Report.privacy_summary: PrivacySummary` (contracts section 8) and the full `PrivacySummary` shape, and no later task happened to touch `Report` to pick it up (`Config.privacy`/`PrivacyConfig` and `EventType.PRIVACY_BLOCK`, added by the same commit, were already present — T3b and T8 needed those directly). The other four commits were behavior-only clarifications with no new field.

Added `PrivacySummary` (`synthetic_marker_found`, `ingest_identifier_hits`, `outbound_prompts_checked`, `outbound_prompts_blocked`, `approved_providers`, `providers_used`) immediately after `JudgeSummary`, matching the contract's own ordering, and `Report.privacy_summary` between `injection_check` and `judge_summary`, matching the contract table's field order. Added the `tests/test_models.py` `SAMPLES` entries the same way every other model gets one; `test_every_contract_has_a_sample` would otherwise fail on any registered `ContractModel` subclass missing a sample, and `test_contract_round_trip_and_fields`/`test_extra_fields_rejected`/`test_required_fields` all run automatically once the sample exists — no bespoke test code was needed beyond the two dict entries. `tests/test_mutation_check.py::test_t1_plan` pins the built-in T1 mutation-plan size; bumped 116 -> 117 for the new shape, the same way it was bumped 115 -> 116 when T3b added `PrivacyConfig`.

#### T1 addendum contract check

| Rule or field touched | Implementation | Test |
|---|---|---|
| Section 8 `Report.privacy_summary: PrivacySummary` | `Report.privacy_summary` field, `PrivacySummary` class, both in `src/council/models.py` | `test_contract_round_trip_and_fields[Report]`, `test_contract_round_trip_and_fields[PrivacySummary]`, `test_every_contract_has_a_sample` |
| Section 8 `PrivacySummary` shape: `synthetic_marker_found`, `ingest_identifier_hits`, `outbound_prompts_checked`, `outbound_prompts_blocked`, `approved_providers`, `providers_used`, all CODE | `PrivacySummary(ContractModel)` | `test_contract_round_trip_and_fields[PrivacySummary]`, `test_extra_fields_rejected[PrivacySummary]`, `test_required_fields[PrivacySummary-*]` |
| Section 9's "Key idea": the model never sets a CODE-owned field | `PrivacySummary` has no draft counterpart; nothing in `agents/` exists yet (Phase 2) to construct it from LLM output, so there is no path for the model to set it | inherited from `ContractModel`'s `extra="forbid"`, same as every other CODE-only aggregate (`JudgeSummary`, `ConfidenceInputs`) |
| Populating `privacy_summary` at runtime (counting prompts checked/blocked, which providers were actually used) | Not implemented — that is T14 (`report.py`) and T8's gateway/trace data, not a T1 model concern | Out of scope here, same as `JudgeSummary`'s and `ConfidenceInputs`' own runtime population, which are also still T6/T14 work |

#### T1 addendum mutation audit

**Tool bug found and fixed.** The first run of this audit found `tools/mutation_check.py` scored two mutations `SURVIVED/ERROR` — `Exact enum Role` and `Shape Argument` — even though both provably broke the suite. Both crash pytest **collection** (an `ImportError`/`ValidationError` raised while pytest imports test files, before any test runs), not an ordinary test failure: mutating `Role.SURG` crashes `tests/conftest.py` importing `council.config`, because `config.py`'s module-level `SPECIALISTS: Final = {Role.SURG, ...}` evaluates at import time (added in T2); removing `Argument.argument_id` crashes collecting `tests/test_scoring.py`, because its `@pytest.mark.parametrize` decorator calls the `argument()` helper eagerly at import time (added in T6). The tool's `killed` check was `run.returncode == 1 and any(expected in line for line in failed)` — a collection error exits nonzero (2, or 4 for a broken `conftest.py`) but is never `1` and never produces a `FAILED ` line, since nothing ran, so it silently fell outside the check.

Fixed in `tools/mutation_check.py` (commit `27aadb7`, "tools: count collection errors as mutation kills"): `killed` is now `run.returncode != 0` — any nonzero exit, on the exit code alone, since the baseline run already confirmed a clean `0` before mutating. Added `test_import_time_crash_is_killed_end_to_end` (`tests/test_mutation_check.py`), an isolated synthetic git repo with its own `pyproject.toml`/`tests/`, whose `conftest.py` imports a target module; mutating that module to crash at import time confirms the tool now reports it killed even though `failed_tests` is empty. Also corrected `test_restore_after_every_outcome`'s `collection_error` case, which had encoded the old, wrong expectation (`killed=False` for exit code 2 with no `FAILED` line).

**The bug's direction was always safe: it could only undercount kills, never overcount them.** A mutation was marked `SURVIVED/ERROR` only when it failed to produce a `returncode == 1` + matching `FAILED` line — which includes every case where the mutation was genuinely caught by a collection error, but never the reverse. Nothing that actually passed (`returncode == 0`, tests still green) could have been misreported as killed. So every mutation any earlier task's dev-log entry reported as `KILLED` really was killed; no earlier task's reported numbers need re-checking. The only failure mode was undercounting — reporting a real kill as `SURVIVED/ERROR` — which is exactly what happened here and would have stopped the audit (`main()` returns 1 on the first `SURVIVED/ERROR`) rather than silently passing something broken.

Re-ran the full built-in T1 plan (117 mutations, no `--spec`) against the current committed `models.py` with the fixed tool:

```powershell
.venv/Scripts/python.exe tools/mutation_check.py --target src/council/models.py
```

**117 / 117 `KILLED`**, entirely by the tool itself — no manual verification needed this time. In particular:

| # | Rule | Exit code | Result |
|---|---|---|---|
| 0 | Exact enum Role | 4 | `KILLED` (previously `SURVIVED/ERROR`, manually verified last entry; now caught automatically) |
| 30 | Shape Argument | 2 | `KILLED` (previously `SURVIVED/ERROR`, manually verified last entry; now caught automatically) |
| 56 | Shape PrivacySummary | 1 | `KILLED` (the new mutation this addendum added; ordinary `test_contract_round_trip_and_fields[PrivacySummary]` failure) |
| all other 114 | (unchanged from the original T1/T3b audits) | 1 | `KILLED` |

Committed code was restored and `git status` was clean after every mutation.

## Checkpoint A

### Human sign-off

I reviewed docs/checkpoint-a.md and ran tools/t6_check_failed_specialist.py myself. A specialist whose Round 1 turn failed was correctly excluded from specialists_counted, dissent, and both confidence terms. Checkpoint A is closed on 2026-09-22.
