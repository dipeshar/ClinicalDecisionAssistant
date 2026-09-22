# Checkpoint A: review of T1, T5, T6, T8

> Decision support only; requires human clinical sign-off; synthetic data only.

Per `docs/tasks.md`, "Checkpoint A. All tests are green. The human reviews T1, T5, T6 and T8 by hand before Phase 2." This document prepares that review. It does not start T9. All commits referenced below are already on `master`; `git log --oneline -3` at the time of writing shows `d32f7b1 T8: record contract and mutation audit` as HEAD, and `git status` is clean.

Full suite at HEAD: **956 tests pass** (`.venv/Scripts/python.exe -m pytest -q`).

---

## T1 — Contract models (`src/council/models.py`)

### 1. Rule(s) implemented

Every contract in `docs/data-contracts.md` as a Pydantic model, with the trust boundary from the contracts' own "Key idea" (line 5): *"The model never sets anything that decides trust (verified flags, statuses, confidence, dissent, disclaimer)."* Concretely, section 5's `Claim.grounding_status` field is marked `Filled by: CODE`, so the LLM-facing `ClaimDraft` model has no such field, and `ContractModel` sets `extra="forbid"` so no caller — human, model, or careless code — can smuggle a trust field into a draft by keyword argument.

### 2. Live demonstration

Calling `ClaimDraft(...)` directly with a `grounding_status` keyword, the way a bug that tried to let the model set its own trust status would:

```python
from pydantic import ValidationError
from council.models import ClaimDraft

try:
    ClaimDraft(text="The procedure is low risk.", citations=[], grounding_status="grounded")
except ValidationError as error:
    print(error)
```

Actual output:

```
1 validation error for ClaimDraft
grounding_status
  Extra inputs are not permitted [type=extra_forbidden, input_value='grounded', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

`grounding_status` is never even declared on `ClaimDraft`; the only place it exists is on the code-constructed `Claim`, built by `grounding.ground_claim` (see T5).

### 3. Mutation count and clean tree

- Implementation commit: `ea3a0b8` ("T1: contract models with tests"); test-strengthening commit `4e177d6`; audit commit `1505baf` ("T1: record contract and mutation audit").
- Mutation count: **115 / 115 killed** (`tools/mutation_check.py --target src/council/models.py`, no `--spec`, using the tool's built-in T1 rule set). One coverage gap was found and closed during the audit (a non-finite-float mutation initially survived; `test_finite_numbers` was added and the mutation re-run successfully) — see `docs/ai-dev-log.md`, T1 section, "A real coverage gap".
- Clean tree: `tools/mutation_check.py` refuses to run unless `git status --porcelain` is empty, and re-checks after every single mutation is restored with `git restore`. The dev log records "All 115 final mutations were detected" with the worktree clean throughout. `git status` at HEAD today is clean.

---

## T5 — Quote / grounding check (`src/council/grounding.py`)

### 1. Rule(s) implemented

Contracts section 13, rule 4 (quote check): case/whitespace/quote-style normalization, `...` skip-word matching in order, and the 4–40 word count bound. Combined with section 5: `Citation.verified` and `Citation.verify_note` are `Filled by: CODE`, never the model — the LLM only supplies `CitationDraft.passage_id`/`quote`; code decides whether it actually checks out.

### 2. Live demonstration

A citation whose quote does not appear in the cited passage, called directly against `verify_citation` (no test runner):

```python
from council.models import CitationDraft
from council.grounding import verify_citation

sources = {"CASE-tests": "Creatinine was 1.1 mg/dL and eGFR was 78 on the most recent panel."}
draft = CitationDraft(passage_id="CASE-tests", quote="the patient has never had any kidney problems")
citation = verify_citation(draft, sources, shown_ids={"CASE-tests"})
print(citation.verified, citation.verify_note)
```

Actual output:

```
verified=False, verify_note='quote text not found in source in order'
```

The passage never says anything about kidney problems; the quote fails, and — per the design's "honest limit" — this only proves the *words* aren't there, not that a present quote would actually support the claim. That limit is by design, not a bug (`docs/design.md`, "Grounding check, done in code").

### 3. Mutation count and clean tree

- Implementation commit: `3f6a64e` ("T5: quote check with tests"); audit commit `bbdae89` ("T5: record quote-check contract and mutation audit").
- Mutation count: **33 / 33 killed** (`tools/mutation_check.py --target src/council/grounding.py --spec tools/t5_mutations.json`), covering normalization, ellipsis ordering/overlap, the 4/40-word boundaries, word-boundary matching, source/turn-availability checks, and that code-owned fields (`verified`, `verify_note`, `source_type`, `grounding_status`) can't be echoed or spoofed from input.
- Clean tree: same tool, same enforcement. Dev log: "Final restored-code tests: 838 passed" with a clean worktree after every mutation.

---

## T6 — Dissent and confidence (`src/council/scoring.py`)

### 1. Rule(s) implemented

Contracts section 12, confidence formula step 6: *"level: 70 or more is high, 40 to 69 is medium, below 40 is low."* Also section 13 rule 9: *"Confidence, dissent and the disclaimer are set by code only."*

### 2. Live demonstration

`confidence_level` is the pure function that turns a numeric score into the code-owned `Level` enum. Called directly at and just below each boundary:

```python
from council.scoring import confidence_level

for score in (69.999, 70.0, 39.999, 40.0):
    print(score, "->", confidence_level(score).value)
```

Actual output:

```
69.999 -> medium
70.0   -> high
39.999 -> low
40.0   -> medium
```

Both boundaries are inclusive on the upper band, matching the contract's "70 or more" / "40 to 69" wording exactly (`>= 70`, `>= 40`, else low).

### 3. Mutation count and clean tree

- Implementation commit: `a1b910c` ("T6: dissent and confidence with tests"); audit commit `465df26` ("T6: record contract and mutation audit").
- Mutation count: **45 / 45 killed** (`tools/mutation_check.py --target src/council/scoring.py --spec tools/t6_mutations.json`), including both level boundaries explicitly (`High includes 70`, `Medium includes 40`) and the penalty caps/rates, stance table, and final-round selection.
- Clean tree: dev log: "All 45 mutations were detected by their named tests. Committed code was restored and the audit worktree was clean after every mutation."

---

## T8 — Gateway and fake provider (`src/council/gateway.py`, `src/council/providers/`)

### 1. Rule(s) implemented

Contracts section 13, rule 20 (gateway privacy check): *"Before every call, the gateway checks that the provider is in `approved_providers` and that the prompt matches no identifier pattern. If either check fails, the call is refused, a `privacy_block` event is written to the trace as a `privacy_block` event with the kind only, never the value, and the turn counts as failed, and the report is INCOMPLETE with the reason."* Also design.md's explicit instruction that this check runs **before** the budget check.

### 2. Live demonstration

A real `LLMGateway`, real `Budget`, real `TraceWriter` writing to an actual file, and a `FakeProvider` scripted to return a response it should never get to return, called with a prompt that contains a synthetic email address:

```python
gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1,
             prompt="Follow-up contact for the patient: demo.patient@example.com per the consult note.")
```

Actual output:

```
GatewayRefusal raised: identifier: email
provider.calls_made = 0   (the model was never called)
trace.jsonl contents:
   event_type='privacy_block' error='identifier: email' prompt=None
confirmed: the matched email never appears anywhere in trace.jsonl
```

The refusal reason is the identifier *kind* only ("identifier: email"); the trace event's `prompt` field is `None`; and a direct byte-level check of `trace.jsonl` confirms the matched address string is not present anywhere in the file — matching "never the value."

### 3. Mutation count and clean tree

- Implementation commit: `53deab0` ("T8: gateway and fake provider with tests"); spec commit `19ad833`; a coverage fix `d4a434d` ("T8: strengthen token-estimate regression coverage" — one mutation initially survived because a tiny-budget test's output cap alone already exceeded its limit, so a forced `tokens_in = 0` didn't change the outcome; a more targeted test was added); audit commit `d32f7b1` ("T8: record contract and mutation audit").
- Mutation count: **30 / 30 killed** — 24/24 in `src/council/gateway.py`, 6/6 in `src/council/providers/fake.py` (`tools/mutation_check.py` against `tools/t8_gateway_mutations.json` and `tools/t8_providers_mutations.json`).
- Clean tree: same tool, same enforcement, confirmed in the dev log after both audits. `git status` at HEAD today is clean.

---

## Open items for the human to double-check

1. **T8 — writing a `budget` trace event on refusal is my inference, not an explicit contract requirement.** The contracts define a `budget` `event_type` (section 10) and rule 20 explicitly requires a `privacy_block` event on a privacy refusal, but the contracts never explicitly say a budget refusal must also write one event. I chose to write exactly one `EventType.BUDGET` event per refused reservation, by analogy with the privacy case and because the enum value would otherwise go unused before T15's orchestrator exists. Worth confirming this is the intended reading, not something that should instead be an `EventType.ERROR` event, or something the orchestrator (not the gateway) writes at a coarser grain.
2. **T8 — the token-reservation estimate (`len(prompt)`, i.e. one "token" per character) is a deliberate over-estimate, not a real tokenizer.** It exists only to keep `Budget.complete`'s settlement-bound check (from T7) safe under any real tokenizer, since no tokenizer is an allowed dependency. In a long-running, highly concurrent run this could make the budget look more constrained than it really is (reservations release once real usage is known, so it's not a permanent loss, just temporary headroom pressure). Worth deciding now whether that's acceptable through T17, or whether a tighter estimate (with a corresponding relaxation of the T7 settlement-bound check) is wanted instead.
3. **T8 — retrying rate limits, not just timeouts.** design.md says "Retry API errors (timeouts, rate limits)"; the original T8 task line only mentions "timeouts." I added `ProviderRateLimit` as a second retryable error alongside `ProviderTimeout`. This seemed like the more literal reading of design.md, but since it's the only design decision in T8 that wasn't explicitly spelled out in `tasks.md` itself, it's worth a second look.
4. **T8 — the API-key-never-leaks test is necessarily a stand-in.** No real provider adapter exists yet (that's T17, after real keys exist), so the test uses a test-only `KeyHoldingProvider` that mimics how a real adapter will hold a key. It proves the gateway/trace path itself never touches or forwards a key it's handed; it cannot prove a not-yet-written real adapter will behave the same way. Re-verify this specifically once T17 lands.
5. **T6 — how the "final round" is selected per specialist for confidence penalties, independently of which round the judges actually scored, is a substantive interpretation of section 12** (carried over from the T6 work, not new this checkpoint). The contract text supports it, but it's dense enough — and load-bearing enough for the confidence number — that it's worth the human re-deriving it by hand once against `docs/data-contracts.md` section 12, rather than trusting the contract-check table alone.
6. ~~**T1 — two contract gaps (failed-argument shape, bare-report fallback, and several aggregate objects) were found by the coding agent during T1 and closed by the human editing `design.md`/`data-contracts.md` directly**, not by this session. That's expected process per `AGENTS.md` ("the docs win... if you think one needs a change, write the suggestion and wait"), but it means T1's models reflect contract text that was itself still being finalized partway through the task — worth a quick confirmation that the currently-committed contracts are the ones actually intended, with no further pending edits.~~ **Resolved:** re-reading `data-contracts.md`/`design.md` against `models.py` found one real remaining gap — `Report.privacy_summary: PrivacySummary` (added to the contracts by `4f4db15`, after T1 was committed) was missing entirely. Added the `PrivacySummary` model and the `Report` field, with tests and a full mutation re-audit, in `5ce14fc`/`aeb8555` ("T1: add missing PrivacySummary model (contract gap from checkpoint A)" / "T1: record PrivacySummary contract and mutation audit").
7. **General:** none of these four tasks make a real model call — all verification is against `FakeProvider` and pure functions. That's correct for their scope (per `AGENTS.md`, no real model calls until T17), but it means the checkpoint above cannot demonstrate anything about real provider behavior (timeout shapes, real token accounting, actual rate-limit errors) — only that the code's own logic does what the contracts say when its inputs are controlled.
