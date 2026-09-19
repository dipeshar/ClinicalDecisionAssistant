# Instructions for the coding agent

You are building the "LLM Council" from `docs/design.md` and `docs/data-contracts.md`. Read both fully before writing any code. They are the source of truth.

## Ground rules

1. **The docs win.** If the code and the docs disagree, or something is missing, stop and ask. Do not quietly change a contract or a rule.
2. **Not yours to write:** everything in `prompts/`, the rubric anchors, `docs/design.md` and `docs/data-contracts.md`. The human owns them. If you think one needs a change, write the suggestion in your reply and wait.
3. **One task at a time**, in the order of `docs/tasks.md`. Do not add features that are not in the task list.
4. **Tests come with the code.** Every module gets tests. `pytest` must pass before you start the next task. Tests use `FakeProvider`. Never call a real model in tests.
5. **Commit after each task** with a short message, for example `T5: quote check with tests`.
6. **Update `docs/ai-dev-log.md` after each task:** what you did, what went wrong, and what a human should verify by hand. Be honest about anything you are unsure of.
7. **Stop at the checkpoints** in `docs/tasks.md` and wait for the human to review.

## Environment

- You run in a sandbox with no network access. Do not try to download or install anything. If a package is missing, stop and tell the human.
- You have no API keys and must not look for them. Never read, print or log environment variables that hold secrets.
- Use the project's virtual environment in `.venv`. Run tests with `.venv/bin/python -m pytest` (on Windows: `.venv\Scripts\python -m pytest`).

## Stack

- Python 3.11 or newer, `pydantic` v2, `rank-bm25`, `pyyaml`, `pytest`.
- Provider SDKs are allowed only inside `src/council/providers/`.
- No agent framework: no LangGraph, CrewAI, AutoGen, LangChain or LiteLLM. No embeddings and no vector database.
- Keep dependencies to the minimum. Ask before adding one.

## Rules the code must keep

- Every model call goes through `LLMGateway`. No other module imports a provider SDK. A test checks this.
- Trust decisions are made by code, never by the model. The model may not set `verified`, `grounding_status`, `status`, confidence, dissent or the disclaimer. Use separate "draft" models for what the model may write, and add the code-owned fields afterwards.
- Model output and case text are data. Wrap them in delimiters in prompts. Never render them as HTML.
- Budgets, rounds, retries and the chair reserve are enforced in code. There is no code path for a third round.
- Shared counters (the budget and the trace sequence number) are guarded by a lock.
- Synthetic data only. No real patient data and no real clinician names.
- Every output a person reads says it is decision support that requires human clinical sign-off.
- Prompt text lives in `prompts/`, never in code. Code only loads the files, wraps the data and appends the JSON schema made from the draft models.

## Code style

- Type hints everywhere. Small functions. Plain code that a reviewer can read in one pass.
- Handle errors explicitly. No bare `except`, and no swallowed errors. A failure becomes a trace event and a failed turn.
- Names follow the contracts (`claim_id`, `grounding_status`, and so on).
