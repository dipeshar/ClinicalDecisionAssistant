# Build plan

The coding agent works through the tasks in order. Each task has a "done when" line. The design is in `design.md` and the exact shapes are in `data-contracts.md`.

## 1. Repo layout

```
llm-council/
  AGENTS.md  README.md (written at the end)
  pyproject.toml
  config.yaml
  docs/
    design.md  data-contracts.md  tasks.md  ai-dev-log.md
    architecture.md  architecture.png  architecture.svg
  cases/
    TEMPLATE.md  README.md
    original/                 the provided sample case, untouched
    cardiac_01.md             the sample, converted into our template
    contrast_02.md            contrasting case
    cardiac_01_injection.md   sample with a hidden instruction
    script_03.md              case with a <script> line
  kb/
    surgeon/  physician/  anaesthesia/  admin/  redteam/
  prompts/                    written by the human (section 3)
  src/council/
    models.py  config.py  ingest.py  scanner.py  kb.py  grounding.py
    scoring.py  budget.py  trace.py  gateway.py  orchestrator.py
    report.py  report_page.py  cli.py
    providers/                base.py  fake.py  <provider_a>.py  <provider_b>.py
    agents/                   prompting.py  specialist.py  judge.py  red_team.py  chair.py
  tests/
  runs/                       committed outputs for the demo cases
  slides/
```

## 2. Knowledge base file format

One Markdown file per topic, inside the role's folder (for example `kb/anaesthesia/asa_classification.md`). Each passage is a `##` heading that is its ID, followed by the passage text.

```markdown
# ASA physical status classification (synthetic summary)

## ANAES-KB-01

ASA class III describes a patient with severe systemic disease that limits activity but is not incapacitating. Examples include poorly controlled diabetes and stable heart failure.

## ANAES-KB-02

...
```

Rules:

- The first `#` heading is the source title. It is saved on every passage in the file.
- A passage ID is `<ROLE>-KB-<nn>`, unique inside the whole KB folder. The loader rejects duplicates and wrong prefixes.
- A passage is 40 to 150 words, so that quotes of 4 to 40 words are possible.
- About 8 to 12 passages per role. Small on purpose.
- Content is synthetic or public-domain. Say "synthetic summary" in the source title. It must never look like real medical advice.
- The red team KB (`kb/redteam`, prefix `RED-KB`) holds the missing-information checklist, contradiction patterns, over-confidence markers and injection patterns.

**Who writes the KB:** draft it with AI once the sample case is known, so the passages match what the case triggers. The human reviews every passage ID and source title by hand.

## 3. Prompt files (the human writes these)

The code loads these, wraps the data and appends the JSON schema. Prompts hold only the role, the instructions and the rules.

| File | What it holds |
|---|---|
| `persona_surg.md`, `persona_phys.md`, `persona_anaes.md`, `persona_admin.md` | Persona, skill emphasis and lean of each specialist |
| `specialist_round1.md` | Round 1 instructions shared by all specialists (grounding, citations, uncertainty) |
| `specialist_round2.md` | Round 2 instructions: answer the strongest opposing claim, use the judge notes, mark each Round 1 claim kept, revised or dropped |
| `judge.md` | Judge instructions: score, flag untraceable claims, write notes (Round 1 only), never comment on which recommendation is right |
| `rubric.md` | The four criteria, with what a 1, a 3 and a 5 mean for each |
| `red_team.md` | The five attack categories and the injection check |
| `chair.md` | Pick a recommendation, cite claim IDs only, one note per specialist, never add claims |
| `repair.md` | The one repair retry: what was wrong and how to fix it |

## 4. Tasks

### Phase 1: everything that needs no real model

| ID | Task | Main files | Done when |
|---|---|---|---|
| T0 | Skeleton | `pyproject.toml`, `src/`, `tests/` | `pytest` runs and `python -m council --help` works |
| T1 | Contract models | `models.py` | Every contract in `data-contracts.md` is a Pydantic model. "Draft" models (what the LLM may write) are separate from full models (with the code-owned fields). JSON round-trip tests pass. Enum values match the contracts. |
| T2 | Config | `config.py`, `config.yaml` | Config loads and is validated. A bad value fails with a clear message. `max_rounds` is not a setting. |
| T3 | Ingest and scanner | `ingest.py`, `scanner.py` | The template parses into `CaseContext` with section IDs, hash and `missing_sections`. The scanner flags the four pattern groups and tags flagged lines. Tests on a clean case and an injection case. |
| T4 | KB and retrieval | `kb.py` | KB files load and IDs are validated. BM25 top 5 is deterministic. The query builder covers Round 1 and Round 2. |
| T5 | Quote check | `grounding.py` | Every quote rule has a test: case, spaces, quote and dash styles, `...`, 4 to 40 words, unknown ID, passage not shown in that turn. |
| T6 | Dissent and confidence | `scoring.py` | The stance table and formula from section 12 of the contracts, with tests for failed turns, the Round 2 fallback, penalty caps, clamping and the level boundaries (70 and 40). |
| T7 | Budget and trace | `budget.py`, `trace.py` | Tokens, calls and time are counted. Only the chair can spend the reserve. Trace lines get unique, increasing `seq` under many parallel threads. Tests for both. |
| T8 | Gateway and fake provider | `gateway.py`, `providers/base.py`, `providers/fake.py` | Budget check, model per role, API retry (2 attempts), one trace event per attempt. A tiny budget refuses the call. A test fails if any module outside `providers/` imports a provider SDK. |

**Checkpoint A.** All tests are green. The human reviews T1, T5, T6 and T8 by hand before Phase 2.

### Phase 2: the council on a real model (needs the prompts)

| ID | Task | Main files | Done when |
|---|---|---|---|
| T9 | Prompt assembly | `agents/prompting.py` | Loads prompt files. Wraps case text, arguments and judge notes in data delimiters. Appends the JSON schema made from the draft models. No prompt text in code. |
| T10 | Specialist, Round 1 | `agents/specialist.py` | Retrieval, gateway call, parse, one repair retry, grounding check. Scripted fake-provider tests: good output, bad JSON then fixed, bad JSON twice (turn failed), bad citation twice (claim ungrounded). |
| T11 | Judges | `agents/judge.py` | One call per judge per round. Shuffled order is recorded. Failed arguments are skipped. Feedback is cut to the limits. Round 2 feedback is empty. |
| T12 | Specialist, Round 2 | `agents/specialist.py` | The prompt has the other three arguments, the specialist's own argument with the code check results, and the judge feedback (no scores). The revisions rule is enforced. Skipped when Round 1 failed. |
| T13 | Red team | `agents/red_team.py` | Findings are checked for real evidence IDs. The injection check lists claims that cite flagged lines. |
| T14 | Chair and report checks | `agents/chair.py`, `report.py` | Chair IDs are checked (final round only). Code fills dissent, confidence and disclaimer. A bare report is written when the chair fails. INCOMPLETE reasons are listed. |
| T15 | Orchestrator | `orchestrator.py` | Two rounds, specialists in parallel, skip to the chair when a budget runs out, no path to a third round. End-to-end fake-provider tests: happy path, one failed specialist, budget exhausted after Round 1. |
| T16 | CLI and human gate | `cli.py` | `python -m council run cases/<file>.md` writes the run folder (contracts section 14) and asks approve, reject or comment. The decision is saved with the report hash. |
| T17 | Real providers, first live run | `providers/<provider_a>.py`, `providers/<provider_b>.py` | Both adapters work. One live run on the sample case. The trace shows the real prompts. The token count is checked against the budget. |

**Checkpoint B.** The human reads one full trace by hand and checks 5 citations against their source passages.

### Phase 3 to 5: cases, page, delivery

| ID | Task | Main files | Done when |
|---|---|---|---|
| T18 | More cases | `cases/`, `runs/` | The contrasting case and the injection case run end to end. The injection line is flagged, tagged and not followed. Fix what breaks. Commit the run folders. |
| T19 | Report page (3-hour cap) | `report_page.py` | `report.html` is built from `run.json`. Every ID opens its panel. The `<script>` case shows as text (test). If the cap is hit, the markdown report is the fallback. |
| T20 | README, slides, recording | `README.md`, `slides/` | Everything the brief lists, including AI-tool usage and "What I would do next for production". |

## 5. If time runs short, cut in this order

1. The report page (fall back to the markdown report).
2. The Round 1 against Round 2 view (keep the data).
3. The different judge model (use one model and say so in the README).

Do not cut: the gateway budget, the grounding check, two judges, the red team with the injection test, the human gate, and the trace.

## 6. Running Codex

Codex reads `AGENTS.md` by itself. It does not read the other docs unless told to, which is why `AGENTS.md` tells it to. By default the agent has no network access and can only write inside the repo.

**Setup, once:**

1. Create the repo, copy these files in, run `git init` and make a first commit.
2. Create a virtual environment named `.venv` and install the dependencies yourself (`pydantic`, `rank-bm25`, `pyyaml`, `pytest`), so Codex does not need the network.
3. Start Codex in the repo root and keep the default sandbox.
4. Ask Codex to summarise its instructions. Check that the summary mentions "the docs win", "one task at a time" and "every model call goes through `LLMGateway`".

**First prompt (T0):**

```
Read AGENTS.md, docs/design.md, docs/data-contracts.md and docs/tasks.md.
Do task T0 only. Run the tests, update docs/ai-dev-log.md, commit, and stop.
Tell me what you did and anything you were unsure about.
```

**Every later task:**

```
Do task T<n> from docs/tasks.md only. Follow AGENTS.md.
Run the tests, update docs/ai-dev-log.md, commit, and stop.
Summarise what you did and anything you were unsure about.
```

**After each task, before the next one:**

7. Read the summary and open the 3 places it lists in the diff.

8. Spot-check one row of the mutation table: break that rule yourself and confirm the test fails.

9. Write one line in the dev log under "What I verified by hand".

**Live model runs (T17 onwards):** run them yourself in your own terminal, with the API keys in your environment variables. Codex never sees the keys. Afterwards, give Codex the run folder if you want help reading a trace or fixing a bug.
