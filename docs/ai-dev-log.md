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
| T0 | | | | |

## Where the tools were not trustworthy

Collect real examples here. Examples of the kind of thing to record: a test that passed but did not test the rule, a citation check that was too loose, a summary that claimed something the code did not do.

-

## What I would tell the next person about using these tools

-
