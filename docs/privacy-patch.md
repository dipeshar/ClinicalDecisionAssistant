# Privacy update: text to apply to the docs

For the coding agent: apply every item below exactly as written. Do not reword anything. Each item names the file and the place. If an "old text" is not found exactly, stop and tell the human instead of guessing. Commit these doc changes on their own, then delete this patch file.

## A. docs/design.md

**A1.** Add this new section directly before the heading `## Report page (local, read-only)`:

~~~
## Privacy barriers

The demo uses only synthetic data, and the system enforces that instead of trusting a rule. There are two gates and a few supporting rules.

**Gate at the door (ingest).**

- A case must carry the synthetic-data line from the template. Without it, ingest rejects the case.
- Ingest scans the whole file, including the title and preamble, for identifiers that look real: email addresses, phone numbers, national ID formats (Aadhaar-like, PAN-like, SSN-like), long ID numbers, dates of birth, web links, IP addresses, and "patient name" or "ID number" style fields.
- Any hit rejects the case before any agent or model sees it. The error names the line number and the kind of identifier. It never prints the value.

**Gate at the exit (gateway).**

- Every prompt is scanned again just before it leaves the process. A hit blocks the call (fail closed) and is written to the trace as a `privacy_block` event with the kind only, never the value. The turn counts as failed, and the report is marked INCOMPLETE with the reason.
- The gateway only calls providers on the approved list in config. A call to any other provider is refused.

**Supporting rules.**

- API keys never appear in the trace or in any run output. A test checks this with a fake key.
- The report and the report page show a privacy line: marker found, identifier hits, prompts checked, prompts blocked, and the providers used.
- The case template has no name field. A case refers to "the patient".

**Honest limit.** The scanner catches identifier formats. It cannot catch a name written inside a sentence. That is why the template has no name field and why the synthetic-data line is required. Production needs real de-identification (see the README).
~~~

**A2.** In the section `## LLM gateway (inside our code)`, replace this old text:

~~~
For each call it does four things:

1. **Check the budget.** If tokens, time or calls are used up, it refuses the call.
2. **Pick the model** for the role from config. Judges use a different model from the specialists.
3. **Retry API errors** (timeouts, rate limits) with a short wait.
4. **Write one trace event:** prompt, output, model, tokens, time.
~~~

with this new text:

~~~
For each call it does five things:

1. **Check privacy.** The provider must be on the approved list, and the prompt must contain no identifier pattern. Otherwise it refuses the call.
2. **Check the budget.** If tokens, time or calls are used up, it refuses the call.
3. **Pick the model** for the role from config. Judges use a different model from the specialists.
4. **Retry API errors** (timeouts, rate limits) with a short wait.
5. **Write one trace event:** prompt, output, model, tokens, time.
~~~

**A3.** In the section `## Test cases`, directly after the item that starts `4. **A case with a` and ends `shows it as text.`, add this item:

~~~
5. **A case with fake identifiers** (an email, a phone number, an ID number), to prove ingest rejects it before any model call, with zero tokens spent.
~~~

## B. docs/data-contracts.md

**B1.** At the end of section 3 (after the paragraph that starts `**Text outside the sections.**`, and before the heading of section 4), add this paragraph:

~~~
**Privacy check.** Ingest requires the synthetic-data marker: the text of `privacy.synthetic_marker` (from config) must appear in the preamble, ignoring case. Ingest also scans the whole file, including the title and preamble, for identifier patterns. The kinds are `email`, `phone`, `national_id`, `long_number`, `date_of_birth`, `url`, `ip_address`, `id_label` and `name_label`. If the marker is missing or any pattern matches, ingest rejects the whole case with an error that gives the line number and the kind. The error never contains the matched text, and no `CaseContext` is built. A rejected case still writes a run folder with a `trace.jsonl` that holds one `privacy_block` event (kind and line number only) and no case text.
~~~

**B2.** In section 8, in the Report table, directly after the row that starts `| injection_check |`, add this row:

~~~
| privacy_summary | PrivacySummary | CODE | Shape below |
~~~

Then, directly after the JudgeSummary table (and before the heading of section 9), add:

~~~
**PrivacySummary**

| Field | Type | Filled by | Notes |
|---|---|---|---|
| synthetic_marker_found | bool | CODE | Always true in a report, because a case without the marker is rejected |
| ingest_identifier_hits | int | CODE | Always 0 in a report, for the same reason |
| outbound_prompts_checked | int | CODE | Prompts scanned by the gateway |
| outbound_prompts_blocked | int | CODE | Prompts the gateway refused because of an identifier pattern |
| approved_providers | list[str] | CODE | From config |
| providers_used | list[str] | CODE | Providers that actually received a prompt |
~~~

**B3.** In section 10 (Trace event), in the `event_type` row, add the value `privacy_block` to the list of values. The row must then list: `start`, `llm_call`, `retrieval`, `validation`, `budget`, `error`, `decision`, `privacy_block`.

**B4.** In section 11 (the config table), add this row at the end of the table:

~~~
| privacy | `synthetic_marker` (text that must appear in every case) and `approved_providers` (list of provider names) | Only approved providers may receive a prompt. Every provider named in `models` must be in the list, once the models are set. |
~~~

**B5.** In section 13 (Rules that code enforces), after rule 18, add these rules:

~~~
19. **Ingest privacy check.** A case without the synthetic marker, or with any identifier pattern anywhere in the file, is rejected before any model call. The error and the trace event hold the kind and line number only, never the matched text.
20. **Gateway privacy check.** Before every call, the gateway checks that the provider is in `approved_providers` and that the prompt matches no identifier pattern. If either check fails, the call is refused, a `privacy_block` event is written, the turn counts as failed, and the report is `INCOMPLETE` with the reason.
21. **No secrets in outputs.** API keys never appear in `trace.jsonl`, `run.json` or any report. `config_snapshot` never contains secrets.
22. **One pattern list.** Ingest and the gateway use the same identifier pattern list, kept in one place, so they cannot drift apart.
~~~

## C. docs/tasks.md

**C1.** In the Phase 1 table, directly after the row that starts `| T3 |`, add this row:

~~~
| T3b | Privacy guard at ingest | `privacy.py`, `ingest.py`, `config.py` | The synthetic marker is required. The identifier patterns (email, phone, national ID formats, long numbers, date of birth, URL, IP address, ID label, name label) live in one clearly named, commented list that the gateway will reuse. A hit rejects the case with the line number and kind, and never prints the value. A rejected case writes a run folder whose trace has one `privacy_block` event. Config loading is extended with the `privacy` section, and every provider named in `models` must be in `approved_providers` once the models are set. Tests: a normal case passes, and normal clinical text (lab values, doses, blood pressure like 150/90, ages, ordinary dates) is not flagged. |
~~~

**C2.** In the T8 row, at the end of the "Done when" cell, add this sentence: `The gateway also runs the privacy check (approved provider, no identifier pattern in the prompt) before the budget check, writes a privacy_block event when it refuses, and never writes API keys to the trace (test with a fake key).`

**C3.** In the T18 row, at the end of the "Done when" cell, add this sentence: `The fake-identifier case is rejected at ingest with zero tokens spent.`

**C4.** In the T19 row, at the end of the "Done when" cell, add this sentence: `The page shows the privacy line (marker, identifier hits, prompts checked and blocked, providers used).`

## D. cases/README.md

**D1.** Replace rule 6 with:

~~~
6. Synthetic data only. No real patient data and no real clinician names. The synthetic-data line from the template must stay, because ingest rejects a case without it.
~~~

**D2.** In the list of files, directly after the line that starts with `- \`script_03.md\``, add:

~~~
- `privacy_04.md`: a case with fake identifiers (an email, a phone number, an ID number), to test that ingest rejects it.
~~~

## E. config.yaml

**E1.** Add this block at the end of the file:

~~~
privacy:
  synthetic_marker: "Synthetic case for a demonstration"
  approved_providers: []   # fill in the providers you actually use, for example [openai, anthropic]
~~~

## F. AGENTS.md

**F1.** In the section "Rules the code must keep", add this bullet:

~~~
- Never print or log a matched identifier value. Log the kind and the line number only.
~~~
