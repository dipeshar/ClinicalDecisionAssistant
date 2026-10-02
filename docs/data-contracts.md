# Data Contracts (v2.1, final for build)

These are the shapes of the data passed between steps. The coding agent will turn them into Pydantic models. The reasons behind them are in `design.md`.

**Key idea:** every field says who fills it. `LLM` means the model writes it. `CODE` means our own code sets it. The model never sets anything that decides trust (verified flags, statuses, confidence, dissent, disclaimer).

## 1. IDs

| Thing | Format | Example |
|---|---|---|
| Run | `run-<date>-<time>-<case>` | `run-20260919-1030-cardiac01` |
| Case section | `CASE-<slug>` | `CASE-tests` |
| KB passage | `<ROLE>-KB-<nn>` | `ANAES-KB-04` |
| Argument | `R<round>-<ROLE>` | `R1-SURG` |
| Claim | `<argument id>-C<n>` | `R1-SURG-C2` |
| Red team finding | `RT-<n>` | `RT-3` |

Role codes: `SURG`, `PHYS`, `ANAES`, `ADMIN` (specialists). `JUDGE_A`, `JUDGE_B`, `RED`, `CHAIR` (structural). The red team KB uses the code `RED`, so its passages look like `RED-KB-02`.

## 2. Case template (fixed headings)

The case Markdown file must have these 8 headings. A missing heading is recorded, not silently ignored. Ingest only handles this template. The provided sample case is converted into it by hand, and the original is kept next to it in the repo.

| Heading | Section ID |
|---|---|
| Patient Profile | `CASE-profile` |
| Diagnoses and History | `CASE-diagnoses` |
| Comorbidities | `CASE-comorbidities` |
| Medications | `CASE-medications` |
| Allergies | `CASE-allergies` |
| Tests and Imaging | `CASE-tests` |
| Proposed Procedure | `CASE-procedure` |
| Consultant Review | `CASE-consultant-review` |

## 3. CaseContext (output of Ingest)

**CaseSection**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| id | str | CODE | From the heading, e.g. `CASE-tests` |
| heading | str | CODE | |
| text | str | CODE | Exact text of the section. Flagged lines carry the tag `[FLAGGED: possible instruction]`. |
| flagged | bool | CODE | True if the scanner found instruction-like text |
| flag_reasons | list[str] | CODE | Which patterns matched |

**CaseContext**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| case_id | str | CODE | |
| source_file | str | CODE | |
| case_hash | str | CODE | SHA-256 of the file, so the trace proves which file was used |
| title | str | CODE | |
| sections | list[CaseSection] | CODE | |
| missing_sections | list[str] | CODE | Expected headings not found |
| injection_flags | list[InjectionFlag] | CODE | `section_id`, `line_number`, `matched_pattern` |

**Injection pattern categories.** `matched_pattern` above, and the gateway's scored check (section 13), both draw from one shared list of four categories: `instruction_override`, `role_spoofing`, `answer_manipulation`, `hidden_text`.

**Text outside the sections.** The title line and anything before the first `##` heading are scanned too. If the scanner flags a line there, ingest rejects the whole case with an error that names the line number, and no `CaseContext` is built. Only section text is ever sent to the agents. The title and preamble never are.

**Privacy check.** Ingest requires the synthetic-data marker: the text of `privacy.synthetic_marker` (from config) must appear in the preamble, ignoring case. Ingest also scans the whole file, including the title and preamble, for identifier patterns. The kinds are `email`, `phone`, `national_id`, `long_number`, `date_of_birth`, `url`, `ip_address`, `id_label` and `name_label`. If the marker is missing or any pattern matches, ingest rejects the whole case with an error that gives the line number and the kind. The error never contains the matched text, and no `CaseContext` is built. A rejected case still writes a run folder with a `trace.jsonl` that holds one `privacy_block` event (kind and line number only) and no case text.

## 4. Knowledge base and retrieval

**Passage**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| id | str | CODE | e.g. `ANAES-KB-04` |
| kb | str | CODE | Which role's KB |
| source_title | str | CODE | Where the excerpt came from |
| text | str | CODE | Exact passage text |

**RetrievalResult** (one per specialist turn)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| role | str | CODE | |
| round | 1 \| 2 | CODE | |
| query | str | CODE | Fixed role keywords, plus case section text. In Round 2 it also includes the summaries of the other three Round 1 arguments and the text of any claims the judges flagged on the specialist's own argument. |
| passages | list[Passage] | CODE | Top 5 (`retrieval_top_k`). In Round 2 the specialist is also shown the passages it cited in Round 1. |
| scores | list[float] | CODE | BM25 score for each passage |

## 5. Argument, Claim, Citation

**Citation**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| passage_id | str | LLM | A case section ID or a KB passage ID |
| quote | str | LLM | Words copied from that passage. `...` may skip words. 4 to 40 words in total. |
| source_type | `case` \| `kb` | CODE | Worked out from the ID prefix |
| verified | bool | CODE | True only if the ID is valid, the passage was available that turn, and the quote passes the quote rules (section 13) |
| verify_note | str | CODE | Why it failed, if it did |

**Claim**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| claim_id | str | CODE | e.g. `R1-SURG-C2` |
| text | str | LLM | One clear statement |
| citations | list[Citation] | LLM | At least 1 needed |
| grounding_status | `grounded` \| `ungrounded` | CODE | Ungrounded if no citation, or any citation still failed after the repair retry |

**Rebuttal** (Round 2 only)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| target_argument_id | str | LLM | Must be a real Round 1 argument from a different role |
| target_claim_id | str | LLM | Must be a claim inside that argument |
| why_strongest | str | LLM | Why this is the strongest opposing claim |
| response_claims | list[Claim] | LLM | The answer, grounded like any other claim. Must contain at least one response claim. |

**Revision** (Round 2 only, one per Round 1 claim of the same specialist)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| round1_claim_id | str | LLM | A claim from this specialist's own Round 1 argument. Each one must appear exactly once. |
| action | `kept` \| `revised` \| `dropped` | LLM | |
| new_claim_index | int or null | LLM | Position (starting at 1) in the Round 2 `claims` list of the claim that replaces it. Required for `kept` and `revised`. Must be null for `dropped`. |
| new_claim_id | str or null | CODE | Worked out from `new_claim_index` |
| reason | str | LLM | Short reason. It should say which judge note or code check it responds to, if any. |

**Argument**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| argument_id | str | CODE | e.g. `R1-SURG` |
| role | role code | CODE | |
| round | 1 \| 2 | CODE | |
| stance | `for` \| `against` \| `conditional`, or null | LLM | Null only when `status` is `failed` (rule 17) |
| summary | str | LLM | Short, about 80 words max |
| claims | list[Claim] | LLM | |
| conditions | list[str] | LLM | What must happen first, if stance is conditional |
| uncertainties | list[str] | LLM | What the specialist does not know |
| rebuttal | Rebuttal or null | LLM | Round 2 only |
| revisions | list[Revision] or null | LLM | Round 2 only. One entry for each of this specialist's Round 1 claims. |
| stance_changed | bool | CODE | Compared with the same role in Round 1 |
| retrieved_passage_ids | list[str] | CODE | What the specialist was shown. In Round 2 this includes the passages it cited in Round 1. |
| repair_used | bool | CODE | True if the one repair retry was used |
| status | `ok` \| `failed` | CODE | Failed only if the JSON was still bad after the repair retry. A failed argument has null `stance`, empty `claims`, `conditions` and `uncertainties`, and null `rebuttal` and `revisions`. |
| failure_reason | str or null | CODE | Why the turn failed. Null when `status` is `ok`. |

## 6. Scores

**Score** (one per judge, per argument)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| judge | `JUDGE_A` \| `JUDGE_B` | CODE | |
| argument_id | str | LLM, verified by CODE | The judge names which argument this score is for. Code confirms it matches the one argument sent in this call. |
| model | str | CODE | Which model scored. Judges use a different model from the specialists. |
| round | 1 \| 2 | CODE | |
| groundedness | int 1-5 | LLM | |
| logic | int 1-5 | LLM | |
| uncertainty | int 1-5 | LLM | |
| counterarguments | int 1-5 or null | LLM | Null in Round 1 |
| justification | dict: criterion to str | LLM | One short reason per score |
| untraceable_claims | list of `{claim_id, reason}` | LLM | Claims the judge cannot trace to a source |
| feedback | list of `{claim_id or null, note}` | LLM | Short notes to the specialist on what to fix. `claim_id` is set when the note is about one claim. Notes are about sourcing, logic and uncertainty, never about which recommendation is right, and contain no scores. Max 5 notes, 40 words each. Round 1 only: in Round 2 it is left empty, because no round follows. |

**Scorecard** (the machine-readable file, `scorecard.json`)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| run_id | str | CODE | |
| scores | list[Score] | CODE | All raw scores |
| skipped_arguments | list[argument_id] | CODE | Failed arguments that were not judged |
| failed_judge_calls | list of `{judge, round, argument_id}` | CODE | Judge calls that still failed after the repair retry (rule 18). A judge can have more than one failed call in the same round, one per argument; each is its own distinct entry. |
| per_argument | list[ArgumentScoreSummary] | CODE | Shape below |
| code_ungrounded_claims | list[claim_id] | CODE | Claim IDs our own check marked ungrounded, so we can compare with what the judges flagged |
| round_comparison | list[RoundComparison] | CODE | Shape below |

A **disagreement** is one argument-and-criterion pair where the two judges differ by `judge_disagreement_gap` (2) or more.

**ArgumentScoreSummary** (one per judged argument)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| argument_id | str | CODE | |
| role | role code | CODE | |
| round | 1 \| 2 | CODE | |
| judges_scored | list[judge] | CODE | Which judges produced a score for this argument. Normally both. |
| mean | `{groundedness, logic, uncertainty, counterarguments}`, each a float or null | CODE | Mean across the judges who scored it. `counterarguments` is null in Round 1. |
| gap | `{groundedness, logic, uncertainty, counterarguments}`, each an int or null | CODE | Absolute difference between the two judges. Null when only one judge scored it, and for `counterarguments` in Round 1. |
| disagreement_count | int | CODE | Number of criteria whose gap is `judge_disagreement_gap` or more. 0 when only one judge scored it. |

**RoundComparison** (one per specialist role)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| role | role code | CODE | |
| shared_score | `{round1, round2, change}`, each a float or null | CODE | Mean of groundedness, logic and uncertainty across judges, per round. `change` is `round2` minus `round1`. Null when either round is missing. Counterarguments is left out because it exists only in Round 2. |
| ungrounded_claims | `{round1, round2}`, each an int or null | CODE | Count per round. Null if that round has no argument. |
| revisions | `{kept, revised, dropped}`, each an int | CODE | Counts from the Round 2 `revisions`. All 0 if there was no Round 2. |
| round2_status | `ok` \| `failed` \| `skipped` | CODE | `skipped` when the Round 1 turn failed |

## 7. Red team

**RedTeamFinding**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| finding_id | str | CODE | `RT-<n>` |
| category | `missing_info` \| `assumption` \| `contradiction` \| `overconfidence` \| `injection` | LLM | |
| severity | `low` \| `medium` \| `high` | LLM | |
| description | str | LLM | |
| evidence_ids | list[str] | LLM | Case sections, arguments, claims, or `RED-KB-nn` passages. Code checks they exist. |
| affected_roles | list[role code] | LLM | |
| suggested_action | str | LLM | e.g. "Get a repeat kidney function test" |

**RedTeamReport**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| findings | list[RedTeamFinding] | LLM | |
| injection_check.scanner_flag_count | int | CODE | From ingest |
| injection_check.claims_citing_flagged_lines | list[claim_id] | CODE | Any claim whose citation points at a flagged line |
| injection_check.verdict | `no_sign` \| `possible_influence` \| `influenced` \| `not_run` | LLM, or CODE when the red team did not run | Did any argument follow an embedded instruction? `not_run` is set by code, never the red team, when this step of the pipeline was skipped (see the new rule below). |
| injection_check.notes | str | LLM | |

## 8. Report

| Field | Type | Filled by | Notes |
|---|---|---|---|
| run_id, case_id | str | CODE | |
| status | `COMPLETE` \| `INCOMPLETE` | CODE | Incomplete if a budget ran out, a specialist turn failed, or the chair failed |
| incomplete_reasons | list[str] | CODE | |
| failed_turns | list[argument_id or role] | CODE | Turns that failed and were left out |
| recommendation | `proceed` \| `proceed_with_modifications` \| `delay_pending_investigation` \| `decline`, or null | CHAIR (LLM) | Null only in a bare report |
| recommendation_basis | list[argument_id] | CHAIR (LLM) | Code checks they exist |
| confidence | Confidence, or null | CODE | Shape below. Formula in section 12. Null in a bare report. |
| council_warning | str or null | CODE | Set when more than half of the specialists dissent |
| strongest_for | list[claim_id] | CHAIR (LLM) | Grounded, final-round claims only. Code rejects others and copies in the claim text. |
| strongest_against | list[claim_id] | CHAIR (LLM) | Same |
| required_actions | list of `{text, source_ids}` | CHAIR (LLM) | Each must point to existing claim or finding IDs |
| role_notes | dict: role to str | CHAIR (LLM) | One short note per non-failed specialist on how its position relates to the recommendation |
| dissent | list of `{role, stance, argument_id, note}` | CODE | Specialists whose final stance is not accepted (section 12). `note` is copied from `role_notes`. |
| red_team_findings | list[RedTeamFinding] | CODE | Copied in full from the red team report |
| injection_check | object | CODE | Copied from the red team report, or code-built with verdict `not_run` if the red team never ran (see the rule above) |
| privacy_summary | PrivacySummary | CODE | Shape below |
| judge_summary | JudgeSummary | CODE | Shape below |
| narrative | str | CHAIR (LLM) | Short summary. Every sentence ends with at least one ID tag such as `[R1-SURG-C2]`. Code checks the tags exist. |
| citations_index | list[Citation] | CODE | Every citation used, with its verified flag |
| disclaimer | str | CODE | Fixed text: decision support only, requires human clinical sign-off, synthetic data |
| human_decision | HumanDecision or null | CODE | Empty until the gate |

**Bare report:** code writes a bare report, status `INCOMPLETE`, in two cases: the chair call fails, or no specialist has a non-failed final argument (every specialist failed). In the second case `incomplete_reasons` includes `"all specialists failed"` and the chair is not called. Either way:

- `recommendation`, `confidence` and `council_warning` set to null.
- Empty lists (`[]`) for `recommendation_basis`, `strongest_for`, `strongest_against`, `required_actions` and `dissent`, an empty dict (`{}`) for `role_notes`, and an empty string for `narrative`.
- Every CODE field filled in as far as the data collected so far allows: `incomplete_reasons`, `failed_turns`, `red_team_findings`, `injection_check`, `judge_summary`, `citations_index` and `disclaimer`.

**Confidence**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| level | `low` \| `medium` \| `high` | CODE | From `score` (section 12) |
| score | float, 0 to 100 | CODE | |
| inputs | ConfidenceInputs | CODE | |

**ConfidenceInputs**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| judge_part | float | CODE | 0 to 100 |
| judge_round_used | 1 \| 2 \| null | CODE | Which round's scores fed `judge_part`. Null if neither round was judged. |
| agreement_part | float | CODE | 0 to 100 |
| specialists_counted | int | CODE | Non-failed specialists |
| specialists_accepting | int | CODE | Those whose final stance the recommendation accepts |
| base | float | CODE | 0.5 times `judge_part` plus 0.5 times `agreement_part` |
| ungrounded_claims | `{count, penalty}` | CODE | Final round only. Penalty is capped at 20. |
| high_severity_findings | `{count, penalty}` | CODE | Penalty is capped at 20. |
| judge_disagreements | `{count, penalty}` | CODE | Final round only. Penalty is capped at 10. |
| total_penalty | float | CODE | Sum of the three penalties |

**JudgeSummary**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| mean_score | `{round1, round2}`, each a float or null | CODE | Mean of every criterion score, across judges and arguments, per round |
| disagreement_count | int | CODE | Disagreements in the final round |
| judges | list of `{judge, model, rounds_scored}` | CODE | `rounds_scored` is a list of round numbers |
| failed_judge_calls | list of `{judge, round, argument_id}` | CODE | Copied from the scorecard |
| round_comparison | list[RoundComparison] | CODE | Copied from the scorecard |
| code_ungrounded_claims | list[claim_id] | CODE | Copied from the scorecard |

**PrivacySummary**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| synthetic_marker_found | bool | CODE | Always true in a report, because a case without the marker is rejected |
| ingest_identifier_hits | int | CODE | Always 0 in a report, for the same reason |
| outbound_prompts_checked | int | CODE | Prompts scanned by the gateway |
| outbound_prompts_blocked | int | CODE | Prompts the gateway refused because of an identifier pattern |
| approved_providers | list[str] | CODE | From config |
| providers_used | list[str] | CODE | Providers that actually received a prompt |

## 9. Human decision

| Field | Type | Filled by | Notes |
|---|---|---|---|
| run_id | str | CODE | |
| decision | `approved` \| `rejected` \| `comment_only` | HUMAN | |
| comment | str | HUMAN | Optional |
| reviewer | str | HUMAN | Free text, fictional name |
| decided_at | timestamp | CODE | |
| report_hash | str | CODE | Hash of the report the human saw, so we know exactly what was approved |

## 10. Trace event (one line in `trace.jsonl`)

| Field | Type | Notes |
|---|---|---|
| run_id, seq | str, int | Order of events in the run. `seq` is assigned under a lock. |
| timestamp | str | |
| step | `ingest` \| `retrieve` \| `specialist` \| `judge` \| `red_team` \| `chair` \| `human` | |
| event_type | `start` \| `llm_call` \| `retrieval` \| `validation` \| `budget` \| `error` \| `decision` \| `privacy_block` \| `injection_block` | |
| role, round | str, int or null | |
| model | str or null | |
| prompt | str or null | Full prompt sent |
| retrieved_passage_ids | list[str] or null | |
| raw_output | str or null | Exactly what the model returned |
| parsed_ref | str or null | ID of the parsed object (argument, score, finding) |
| tokens_in, tokens_out | int or null | |
| latency_ms | int or null | |
| attempt | int | API attempt number: 1 or 2 |
| repair | bool | True if this call is the repair retry |
| budget_tokens_used | int | Total tokens used after this event |
| error | str or null | |
| finish_reason | str or null | Why the model stopped: "stop", "length", or similar. Null on a failed call with no response. |
| reasoning | str or null | The model's internal reasoning content, when requested and returned. Null otherwise. |

## 11. Budget and config

**Config** (starting values, to tune after the first runs)

| Setting | Starting value | Notes |
|---|---|---|
| max_rounds | 2 | A constant in code, not a setting. There is no third-round path. |
| max_tokens_per_call | specialist 6000, judge 900, red team 3000, chair 7000 | Output cap per call |
| max_total_tokens | 800000 | Starting value was 200,000, raised once a real, mostly-successful run showed genuine cumulative usage approaching that ceiling — not a failure, evidence the pipeline was finally completing most of its calls. OpenRouter's real per-token cost makes a much larger ceiling essentially free. The reservation made before a call is attempted counts one character as one token, a guaranteed upper bound — no real tokenizer produces more tokens than there are characters in the text. This was briefly changed to a closer average estimate, which was reverted after it caused a real settlement failure: an estimate that's merely usually-safe isn't a reservation, since 'usually' means it can be exceeded. The 800,000 total budget, not a tighter individual estimate, is what actually prevents a premature refusal near the end of a run. |
| max_calls | 60 | Counts every attempt. Raised from 40 once judging moved to one call per argument. |
| max_seconds_total | 3600 | Starting value, to tune for your own rate limits and patience. See design.md, "Tuning the budgets for your situation." |
| chair_reserve | 10000 tokens, 60 seconds, 2 calls | Only the chair can spend this. Other roles stop at the maximum minus the reserve. |
| max_repair_retries_per_turn | 1 | Shared by bad JSON and bad citations |
| max_api_attempts | 2 | The first try plus 1 retry |
| judge_disagreement_gap | 2 | |
| judge_feedback | max 5 notes per argument, 40 words each | Extra notes are cut by code |
| retrieval_top_k | 5 | |
| quote_words | 4 to 40 | Total words in a citation quote |
| temperature | specialists 0.4, judges 0, red team 0.5, chair 0.2 | Starting values. Used only if the model allows it. |
| reasoning_effort | specialists/chair/red_team low, judges unset | Passed to the provider on models that support it (currently openai/gpt-oss-120b). Neither judge model supports reasoning controls, so no reasoning parameter is sent for judge calls. |
| models | specialist: openrouter/openai/gpt-oss-120b; chair: openrouter/openai/gpt-oss-120b; red_team: openrouter/openai/gpt-oss-120b; judge_a: openrouter/qwen/qwen3-235b-a22b-2507; judge_b: openrouter/meta-llama/llama-3.3-70b-instruct | Specialists and chair share one model. Judge A and Judge B each use a different model family from the specialists and from each other. |
| privacy | `synthetic_marker` (text that must appear in every case) and `approved_providers` (list of provider names) | Only approved providers may receive a prompt. Every provider named in `models` must be in the list, once the models are set. |
| injection_scoring | weights per pattern category; threshold.default and threshold.chair | Same pattern categories as the ingest scanner. default applies to specialists, judges, and red team, who all read the case directly; chair is looser, since it never does. |

**BudgetState** (kept by the gateway): `tokens_used`, `calls_used`, `started_at`, `exhausted` (bool), `reason`. It is guarded by a lock.

## 12. Dissent and confidence

**Accepted stances.** A recommendation accepts these specialist stances:

| Recommendation | Accepted stances |
|---|---|
| `proceed` | `for` |
| `proceed_with_modifications` | `for`, `conditional` |
| `delay_pending_investigation` | `conditional`, `against` |
| `decline` | `against` |

A specialist whose final stance is not in the accepted list is a **dissenter**. The final stance is the Round 2 stance, or the Round 1 stance if Round 2 was skipped for that specialist, whether because its own Round 2 turn failed or because Round 2 did not run at all (for example, the budget ran out after Round 1). Failed turns are ignored. If more than half of the non-failed specialists dissent, `council_warning` is set.

**Confidence formula** (all in code, with a unit test):

1. `judge_part` = (mean judge score of Round 2 arguments, across all criteria, judges and arguments, minus 1) divided by 4, times 100. If Round 2 was not judged, use Round 1. If neither round was judged, `judge_part` is 0, so missing evidence lowers the confidence.
2. `agreement_part` = share of non-failed specialists whose final stance is accepted, times 100.
3. `base` = 0.5 times `judge_part`, plus 0.5 times `agreement_part`.
4. Penalties, counted on the final round only (Round 2, or Round 1 when Round 2 was skipped for that specialist, whether its own turn failed or the round did not run). A claim that was fixed or dropped in Round 2 is therefore not punished again:
   - 5 per ungrounded claim in the final round (max 20)
   - 10 per high-severity red-team finding (max 20)
   - 5 per judge disagreement in the final round (max 10)
5. `score` = `base` minus penalties, kept between 0 and 100.
6. `level`: 70 or more is `high`, 40 to 69 is `medium`, below 40 is `low`.

`confidence.inputs` stores `judge_part`, `agreement_part`, `base`, and each penalty, so the report page can show how the score was made.

## 13. Rules that code enforces

1. Every LLM output must parse into its contract. Before parsing, a code fence that wraps the entire response (some models always answer inside ```json ... ```) is stripped; this is not a repair and does not cost the turn's retry, since it is a formatting habit, not a content problem. A response with only an opening fence and no closing one is left unchanged. If parsing still fails, one repair retry. If the JSON is still bad, the turn is `failed`. The repair call also fixes bad citations at the same time. Its user message includes the previous attempt's `raw_output` verbatim as labeled, delimited data alongside the original input data and the schema. This block is kept clearly separate from the trusted repair instructions because model-generated output is untrusted and has not been verified by code.
2. A claim needs at least 1 citation, or it is `ungrounded`.
3. A cited ID must exist, and it must be a case section or a passage the specialist was shown in that turn. In Round 2 this includes the passages it cited in Round 1.
4. **Quote check.** Ignore upper and lower case, extra spaces, and quote or dash styles. Split the quote at `...` and require each part to appear in the passage, in order. The whole quote must be 4 to 40 words. If a citation still fails after the repair retry, its claim is `ungrounded`. This proves the quote exists, not that it supports the claim.
5. A rebuttal target must be a real Round 1 argument from a different role, and `target_claim_id` must be a claim inside it. Its `response_claims` must contain at least one claim. An empty list is a validation failure eligible for the same repair retry as other response validation failures.
6. Each non-failed argument of a round is judged with its own call, per judge. A failed judge call for one argument does not affect calls for other arguments.
7. Red team evidence IDs must exist.
8. Chair IDs (basis, strongest claims, actions, narrative tags) must exist. The basis and the strongest claims must come from the final round (Round 2, or Round 1 when Round 2 was skipped for that specialist), so a claim that was dropped cannot be cited as strongest. Strongest claims must also be `grounded`. The chair's claim text is copied in by code, not retyped.
9. Confidence, dissent and the disclaimer are set by code only.
10. The gateway checks the budget before every LLM call. Other roles stop at the maximum minus the chair reserve. If a budget is exhausted, skip to the chair and mark the report `INCOMPLETE`. If the chair call fails, write a bare report.
11. The report page shows case text and model output as plain text only, never as HTML.
12. The budget counter and the trace sequence number are guarded by a lock.
13. **Round 2 revisions.** Every Round 1 claim of that specialist must appear exactly once in `revisions`. `kept` and `revised` need a valid `new_claim_index` that points to a claim in the Round 2 argument. `dropped` must not have one. The Round 2 argument must keep at least 1 claim. If not, the repair retry applies.
14. **Feedback to specialists.** Code passes only the judges' `feedback` and `untraceable_claims` fields, plus its own check results. It never passes the numeric scores or the `justification` text. Notes beyond the limit are cut. Notes are wrapped as data in the prompt, like arguments.
15. Judges do not receive Round 1 scores when they score Round 2.
16. A specialist whose Round 1 turn failed is not run in Round 2. It stays failed.
17. **Failed argument.** `stance` is null if and only if `status` is `failed`. A failed argument has empty `claims`, `conditions` and `uncertainties`, null `rebuttal` and `revisions`, and a `failure_reason`.
18. **Failed judge call.** If a judge's call still fails after the repair retry, the run continues with the other judge. The call is listed in `failed_judge_calls` and the report is `INCOMPLETE`. For arguments that only one judge scored, `mean` is that judge's scores, `gap` is null and `disagreement_count` is 0. If neither judge scored a round, that round has no scores and no notes.
19. **Ingest privacy check.** A case without the synthetic marker, or with any identifier pattern anywhere in the file, is rejected before any model call. The error and the trace event hold the kind and line number only, never the matched text.
20. **Gateway privacy check.** Before every call, the gateway checks that the provider is in `approved_providers` and that the prompt matches no identifier pattern. If either check fails, the call is refused, a `privacy_block` event is written, the turn counts as failed, and the report is `INCOMPLETE` with the reason.
21. **No secrets in outputs.** API keys never appear in `trace.jsonl`, `run.json` or any report. `config_snapshot` never contains secrets.
22. **One pattern list.** Ingest and the gateway use the same identifier pattern list, kept in one place, so they cannot drift apart.
23. **Budget refusal event.** When the gateway refuses a call because the reservation would exceed a budget limit (tokens, calls, seconds, or the chair reserve), it writes exactly one `EventType.BUDGET` trace event recording which limit was hit and the amount requested versus what remained. It does not include the prompt. The refused turn counts as failed, the same as a privacy refusal (rule 20).
24. **Binding judge concerns in Round 2.** A Round 1 claim that both judges named — each independently, as a `feedback` note with that `claim_id`, or by listing it in `untraceable_claims`, in either combination — cannot be marked `kept` in the specialist's Round 2 `revisions`. A claim named by only one judge is not binding. Code checks this after the specialist's Round 2 response is otherwise valid: if any `revisions` entry marks such a doubly-named claim `kept`, treat this as a validation failure eligible for the same repair retry as a bad citation or bad shape (rule 1). If it is still `kept` after the retry, code overrides it: remove it from the Round 2 `claims` list, set its `revisions` entry to `action: dropped`, `new_claim_index: null`, and replace `reason` with a fixed code-generated note stating both judges flagged the claim. Record the override as a trace validation event naming the claim id. This does not fail the specialist's turn; the rest of the Round 2 argument stands as submitted.
25. **Judge response matching.** A judge's response must carry the `argument_id` of the one argument it was actually sent. If it doesn't match, this is a validation failure eligible for the same repair retry as a bad citation or bad shape (rule 1). If it is still wrong after the retry, that judge's call for that argument is treated as failed (rule 18): the run continues without that score, and the report is marked INCOMPLETE with the reason.
26. **Injection check when the red team did not run.** If the pipeline reaches the report without ever running the red team — the budget ran out before that step, or every specialist failed and the run went straight to a bare report — code builds `injection_check` itself rather than copying it from a `RedTeamReport`, which doesn't exist in this case. `scanner_flag_count` and `claims_citing_flagged_lines` are computed the same way they always are, from ingest and whatever claims do exist. `verdict` is set to `not_run`, and `notes` is a fixed message stating the red team did not run and why. `red_team_findings` is an empty list. This keeps the scanner's real findings visible even when the qualitative check was never reached, instead of losing them or inventing a verdict the system never formed.

27. **Deduplicated source passages in judge prompts.** When a judge is shown one or more arguments, every KB passage and case section cited anywhere in those arguments is written out in full exactly once, in a shared block, keyed by its ID. Each citation within an argument shows only its `passage_id` and its own quote, not the passage's full text again. This preserves everything the judge needs to check whether a citation supports its claim; it removes only the repeated copies of the same source text.

28. **A minimal view for the chair.** The chair's prompt shows each final-round argument as: role, stance, and per claim: `claim_id`, text, and `grounding_status`. Conditions are included only when the stance is conditional. Citation quote text, uncertainties, the rebuttal object, and the Round 2 revision history are not shown to the chair — none of these are things the chair's own instructions ask it to use, and including them was an implementation gap against those instructions, not a deliberate design choice.

29. **Gateway-level injection scoring.** In addition to the identifier check (rule 20), the gateway scores every outbound prompt, system and user combined, against the same weighted injection pattern list ingest uses (section 3). If the total score meets or exceeds the role's configured threshold, the call is refused, an `injection_block` trace event is written (kind, matched pattern names, and total score only, never the matched text), and the turn counts as failed immediately, with no repair retry — resending identical content would be blocked identically. Specialists, judges, and the red team share the stricter threshold, since all three read the case document directly. The chair, which never reads the case directly, uses a looser threshold.

## 14. Run folder

Each run writes one folder, `runs/<run_id>/`:

| File | What it holds |
|---|---|
| `trace.jsonl` | Every event (section 10) |
| `run.json` | One bundle. Shape below. |
| `scorecard.json` | Scores only, machine-readable |
| `report.md` | Report for reading in a terminal or on GitHub |
| `report.html` | Clickable report page, built from `run.json` |

The run folder is built in two stages. T16 writes `trace.jsonl`, `run.json`, `scorecard.json`, and `report.md` at the end of a run. `report.html` does not exist until T19 runs separately on an existing run folder and adds it. A run folder produced by T16 alone, before T19 exists, is a complete and valid run folder with one file fewer than the table above — nothing should assume `report.html` is present until T19 has actually run.

`python -m council report` tolerates and ignores unknown fields when loading an existing `run.json`, since a run's output may have been written under an earlier version of these contracts. This applies only to reading a saved run back for display; parsing a model's live output stays exactly as strict as every other contract in this document.

`run.json` exists so the page needs nothing else. Every ID in the report can be looked up in this one file.

**RunBundle** (`run.json`)

| Field | Type | Notes |
|---|---|---|
| run_id, case_id | str | |
| created_at | timestamp | |
| config_snapshot | object | The settings used for the run (models, budgets, limits). Never contains secrets. |
| case_context | CaseContext | |
| retrievals | list[RetrievalResult] | Every specialist turn, both rounds |
| arguments | list[Argument] | Both rounds, including failed ones |
| scorecard | Scorecard | |
| red_team | RedTeamReport or null | Null if the red team did not run |
| report | Report | |
| sources | dict: passage ID to `{source_type, source_title, text}` | Full text of every case section and KB passage cited by a claim or used as red team evidence. `source_title` is the section heading for case sections. |
