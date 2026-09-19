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
| response_claims | list[Claim] | LLM | The answer, grounded like any other claim |

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
| stance | `for` \| `against` \| `conditional` | LLM | |
| summary | str | LLM | Short, about 80 words max |
| claims | list[Claim] | LLM | |
| conditions | list[str] | LLM | What must happen first, if stance is conditional |
| uncertainties | list[str] | LLM | What the specialist does not know |
| rebuttal | Rebuttal or null | LLM | Round 2 only |
| revisions | list[Revision] or null | LLM | Round 2 only. One entry for each of this specialist's Round 1 claims. |
| stance_changed | bool | CODE | Compared with the same role in Round 1 |
| retrieved_passage_ids | list[str] | CODE | What the specialist was shown. In Round 2 this includes the passages it cited in Round 1. |
| repair_used | bool | CODE | True if the one repair retry was used |
| status | `ok` \| `failed` | CODE | Failed only if the JSON was still bad after the repair retry |

## 6. Scores

**Score** (one per judge, per argument)

| Field | Type | Filled by | Notes |
|---|---|---|---|
| judge | `JUDGE_A` \| `JUDGE_B` | CODE | |
| argument_id | str | CODE | Must be a real, non-failed argument |
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
| presented_order | dict: `"<judge>-R<round>"` to list[argument_id] | CODE | The shuffled order each judge saw |
| skipped_arguments | list[argument_id] | CODE | Failed arguments that were not judged |
| per_argument | list | CODE | Per argument: mean per criterion, gap between judges per criterion, and `disagreement_count` |
| code_ungrounded_claims | list[claim_id] | CODE | Claim IDs our own check marked ungrounded, so we can compare with what the judges flagged |
| round_comparison | list | CODE | One entry per specialist: mean judge score in Round 1 and in Round 2 on the three shared criteria (groundedness, logic, uncertainty), the change between them, the count of ungrounded claims in each round, and how many claims were kept, revised and dropped. Counterarguments is left out because it exists only in Round 2. |

A **disagreement** is one argument-and-criterion pair where the two judges differ by `judge_disagreement_gap` (2) or more.

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
| injection_check.verdict | `no_sign` \| `possible_influence` \| `influenced` | LLM | Did any argument follow an embedded instruction? |
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
| confidence | `{level: low\|medium\|high, score: 0-100, inputs}`, or null | CODE | Formula in section 12. Null in a bare report. |
| council_warning | str or null | CODE | Set when more than half of the specialists dissent |
| strongest_for | list[claim_id] | CHAIR (LLM) | Grounded, final-round claims only. Code rejects others and copies in the claim text. |
| strongest_against | list[claim_id] | CHAIR (LLM) | Same |
| required_actions | list of `{text, source_ids}` | CHAIR (LLM) | Each must point to existing claim or finding IDs |
| role_notes | dict: role to str | CHAIR (LLM) | One short note per non-failed specialist on how its position relates to the recommendation |
| dissent | list of `{role, stance, argument_id, note}` | CODE | Specialists whose final stance is not accepted (section 12). `note` is copied from `role_notes`. |
| red_team_findings | list[RedTeamFinding] | CODE | Copied in full from the red team report |
| injection_check | object | CODE | Copied from the red team report |
| judge_summary | object | CODE | From the scorecard, including `round_comparison` |
| narrative | str | CHAIR (LLM) | Short summary. Every sentence ends with at least one ID tag such as `[R1-SURG-C2]`. Code checks the tags exist. |
| citations_index | list[Citation] | CODE | Every citation used, with its verified flag |
| disclaimer | str | CODE | Fixed text: decision support only, requires human clinical sign-off, synthetic data |
| human_decision | HumanDecision or null | CODE | Empty until the gate |

**Bare report:** if the chair call fails, code writes a report with `recommendation` and `confidence` null, status `INCOMPLETE`, and only the CODE fields filled in.

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
| event_type | `start` \| `llm_call` \| `retrieval` \| `validation` \| `budget` \| `error` \| `decision` | |
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

## 11. Budget and config

**Config** (starting values, to tune after the first runs)

| Setting | Starting value | Notes |
|---|---|---|
| max_rounds | 2 | A constant in code, not a setting. There is no third-round path. |
| max_tokens_per_call | specialist 1500, judge 2500, red team 2500, chair 3000 | Output cap per call |
| max_total_tokens | 200000 | Input plus output, all roles. Round 2 prompts are larger (own argument, judge notes, three other arguments), so check the count after the first run. |
| max_calls | 40 | Counts every attempt |
| max_seconds_total | 600 | |
| chair_reserve | 10000 tokens, 60 seconds, 2 calls | Only the chair can spend this. Other roles stop at the maximum minus the reserve. |
| max_repair_retries_per_turn | 1 | Shared by bad JSON and bad citations |
| max_api_attempts | 2 | The first try plus 1 retry |
| judge_disagreement_gap | 2 | |
| judge_feedback | max 5 notes per argument, 40 words each | Extra notes are cut by code |
| retrieval_top_k | 5 | |
| quote_words | 4 to 40 | Total words in a citation quote |
| temperature | specialists 0.4, judges 0, red team 0.5, chair 0.2 | Starting values. Used only if the model allows it. |
| models | Set per role | Specialists and chair share one model. Judges A and B use a different one. |

**BudgetState** (kept by the gateway): `tokens_used`, `calls_used`, `started_at`, `exhausted` (bool), `reason`. It is guarded by a lock.

## 12. Dissent and confidence

**Accepted stances.** A recommendation accepts these specialist stances:

| Recommendation | Accepted stances |
|---|---|
| `proceed` | `for` |
| `proceed_with_modifications` | `for`, `conditional` |
| `delay_pending_investigation` | `conditional`, `against` |
| `decline` | `against` |

A specialist whose final stance is not in the accepted list is a **dissenter**. The final stance is the Round 2 stance, or the Round 1 stance if the Round 2 turn failed. Failed turns are ignored. If more than half of the non-failed specialists dissent, `council_warning` is set.

**Confidence formula** (all in code, with a unit test):

1. `judge_part` = (mean judge score of Round 2 arguments, across all criteria, judges and arguments, minus 1) divided by 4, times 100. If Round 2 was not judged, use Round 1.
2. `agreement_part` = share of non-failed specialists whose final stance is accepted, times 100.
3. `base` = 0.5 times `judge_part`, plus 0.5 times `agreement_part`.
4. Penalties, counted on the final round only (Round 2, or Round 1 for a specialist whose Round 2 turn failed). A claim that was fixed or dropped in Round 2 is therefore not punished again:
   - 5 per ungrounded claim in the final round (max 20)
   - 10 per high-severity red-team finding (max 20)
   - 5 per judge disagreement in the final round (max 10)
5. `score` = `base` minus penalties, kept between 0 and 100.
6. `level`: 70 or more is `high`, 40 to 69 is `medium`, below 40 is `low`.

`confidence.inputs` stores `judge_part`, `agreement_part`, `base`, and each penalty, so the report page can show how the score was made.

## 13. Rules that code enforces

1. Every LLM output must parse into its contract. If not, one repair retry. If the JSON is still bad, the turn is `failed`. The repair call also fixes bad citations at the same time.
2. A claim needs at least 1 citation, or it is `ungrounded`.
3. A cited ID must exist, and it must be a case section or a passage the specialist was shown in that turn. In Round 2 this includes the passages it cited in Round 1.
4. **Quote check.** Ignore upper and lower case, extra spaces, and quote or dash styles. Split the quote at `...` and require each part to appear in the passage, in order. The whole quote must be 4 to 40 words. If a citation still fails after the repair retry, its claim is `ungrounded`. This proves the quote exists, not that it supports the claim.
5. A rebuttal target must be a real Round 1 argument from a different role, and `target_claim_id` must be a claim inside it.
6. Judges must score every non-failed argument of a round once, and only real argument IDs. Argument order is shuffled per judge and round, and recorded in `presented_order`.
7. Red team evidence IDs must exist.
8. Chair IDs (basis, strongest claims, actions, narrative tags) must exist. The basis and the strongest claims must come from the final round (Round 2, or Round 1 for a specialist whose Round 2 turn failed), so a claim that was dropped cannot be cited as strongest. Strongest claims must also be `grounded`. The chair's claim text is copied in by code, not retyped.
9. Confidence, dissent and the disclaimer are set by code only.
10. The gateway checks the budget before every LLM call. Other roles stop at the maximum minus the chair reserve. If a budget is exhausted, skip to the chair and mark the report `INCOMPLETE`. If the chair call fails, write a bare report.
11. The report page shows case text and model output as plain text only, never as HTML.
12. The budget counter and the trace sequence number are guarded by a lock.
13. **Round 2 revisions.** Every Round 1 claim of that specialist must appear exactly once in `revisions`. `kept` and `revised` need a valid `new_claim_index` that points to a claim in the Round 2 argument. `dropped` must not have one. The Round 2 argument must keep at least 1 claim. If not, the repair retry applies.
14. **Feedback to specialists.** Code passes only the judges' `feedback` and `untraceable_claims` fields, plus its own check results. It never passes the numeric scores or the `justification` text. Notes beyond the limit are cut. Notes are wrapped as data in the prompt, like arguments.
15. Judges do not receive Round 1 scores when they score Round 2.
16. A specialist whose Round 1 turn failed is not run in Round 2. It stays failed.

## 14. Run folder

Each run writes one folder, `runs/<run_id>/`:

| File | What it holds |
|---|---|
| `trace.jsonl` | Every event (section 10) |
| `run.json` | One bundle: case context, all arguments, red team report, scorecard, report, and the full text of every passage that was cited |
| `scorecard.json` | Scores only, machine-readable |
| `report.md` | Report for reading in a terminal or on GitHub |
| `report.html` | Clickable report page, built from `run.json` |

`run.json` exists so the page needs nothing else. Every ID in the report can be looked up in this one file.
