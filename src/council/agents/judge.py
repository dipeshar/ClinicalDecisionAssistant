"""Judges: one call per judge per round, scoring every non-failed argument at once.

One judge call: skip failed arguments, shuffle the non-failed arguments of
the round (recording the shuffled order, to reduce position bias per
design.md), assemble the prompt with each argument's cited passages shown in
full, call the gateway, parse the response as one `ScoreDraft` per argument
(rule 1's shared repair retry applies here too), and turn each into a
CODE-owned `Score`. Round 1 feedback is truncated to the configured limits;
Round 2 feedback is always empty, and Round 2 always needs a counterarguments
score, regardless of what the model wrote for either (contracts section 6).
"""

from collections.abc import Callable, Mapping, MutableSequence, Sequence
from pathlib import Path
import random

from pydantic import TypeAdapter

from council.agents import prompting
from council.agents.prompting import RepairIssue
from council.agents.specialist import call_and_parse_with_repair, render_case
from council.gateway import LLMGateway
from council.models import Argument, CaseContext, Config, Round, Score, ScoreDraft, Step, Role

JUDGE_SCHEMA: TypeAdapter[list[ScoreDraft]] = TypeAdapter(list[ScoreDraft])


def render_argument(argument: Argument, sources: Mapping[str, str]) -> str:
    """The argument's full content, with each citation's actual source text
    alongside it, per judge.md: "the actual text of those passages, not just
    their IDs, so you can check whether a citation really supports what it's
    used for."""
    lines = [f"### {argument.argument_id} ({argument.role.value}, round {argument.round})",
             f"Stance: {argument.stance}", f"Summary: {argument.summary}", "", "Claims:"]
    for claim in argument.claims:
        lines.append(f"- [{claim.claim_id}] {claim.text}")
        for citation in claim.citations:
            source_text = sources.get(citation.passage_id, "(source not available)")
            lines.append(f"  - cites {citation.passage_id}: \"{citation.quote}\" — source: {source_text}")
    if argument.conditions:
        lines.append("Conditions: " + "; ".join(argument.conditions))
    if argument.uncertainties:
        lines.append("Uncertainties: " + "; ".join(argument.uncertainties))
    if argument.rebuttal is not None:
        rebuttal = argument.rebuttal
        lines.append(f"Rebuttal targets {rebuttal.target_claim_id} ({rebuttal.target_argument_id}): "
                     f"{rebuttal.why_strongest}")
        for claim in rebuttal.response_claims:
            lines.append(f"- [{claim.claim_id}] {claim.text}")
    return "\n".join(lines)


def truncate_feedback(feedback: Sequence[dict], max_notes: int, max_words: int) -> list[dict]:
    """Extra notes beyond `max_notes` are cut; each kept note's text is cut to
    `max_words` words (contracts section 11 config: "Extra notes are cut by code")."""
    kept = list(feedback)[:max_notes]
    return [{"claim_id": note["claim_id"], "note": " ".join(note["note"].split()[:max_words])} for note in kept]


def build_score(judge: Role, argument_id: str, model: str, round_number: Round, draft: ScoreDraft,
                config: Config) -> Score:
    """Force the round-dependent fields (contracts section 6) rather than trust the
    model: Round 1 never has a counterarguments score, Round 2 never has feedback."""
    counterarguments = None if round_number == 1 else draft.counterarguments
    feedback = [] if round_number == 2 else truncate_feedback(
        [note.model_dump() for note in draft.feedback], config.judging.feedback_max_notes,
        config.judging.feedback_max_words,
    )
    return Score(
        judge=judge, argument_id=argument_id, model=model, round=round_number,
        groundedness=draft.groundedness, logic=draft.logic, uncertainty=draft.uncertainty,
        counterarguments=counterarguments, justification=draft.justification,
        untraceable_claims=draft.untraceable_claims, feedback=feedback,
    )


def run_judge(
    judge: Role, round_number: Round, arguments: Sequence[Argument], case: CaseContext,
    passage_sources: Mapping[str, str], config: Config, gateway: LLMGateway,
    prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
    shuffle: Callable[[MutableSequence[Argument]], None] = random.shuffle,
) -> tuple[list[Score], list[str], bool]:
    """One judge's call for one round. Returns (scores, presented_order, failed).

    `presented_order` is the shuffled argument IDs actually shown, in the order
    shown (contracts: `Scorecard.presented_order["<judge>-R<round>"]`). Empty
    scores and an empty order with `failed=False` mean there was nothing to
    score (every argument of that round failed, or none exist yet); `failed=True`
    means the call itself could not be used (rule 18: the run continues with the
    other judge).
    """
    eligible = [argument for argument in arguments
               if argument.round == round_number and argument.status != "failed"]
    if not eligible:
        return [], [], False

    shown = list(eligible)
    shuffle(shown)
    presented_order = [argument.argument_id for argument in shown]

    sources: dict[str, str] = {section.id: section.text for section in case.sections}
    sources.update(passage_sources)

    data_blocks = [("Case", render_case(case))]
    data_blocks.extend((argument.argument_id, render_argument(argument, sources)) for argument in shown)
    body = prompting.judge_body(data_blocks, prompts_dir)

    def find_issues(scores: list[ScoreDraft]) -> list[RepairIssue]:
        if len(scores) != len(shown):
            return [RepairIssue("Response", f"expected {len(shown)} scores, one per argument shown, "
                                            f"got {len(scores)}")]
        if round_number == 2:
            return [RepairIssue(f"Score for {argument.argument_id}",
                                "counterarguments score is required in Round 2")
                    for argument, score in zip(shown, scores) if score.counterarguments is None]
        return []

    draft, _repair_used, failure_reason, model = call_and_parse_with_repair(
        gateway, role=judge, step=Step.JUDGE, round_number=round_number, body=body,
        schema_model=JUDGE_SCHEMA, prompts_dir=prompts_dir, retrieved_ids=[], find_issues=find_issues,
    )

    if draft is None:
        assert failure_reason is not None  # call_and_parse_with_repair always explains a None draft
        return [], [], True

    assert model is not None  # a successful draft always came from a real gateway call
    scores = [build_score(judge, argument.argument_id, model, round_number, score_draft, config)
              for argument, score_draft in zip(shown, draft)]
    return scores, presented_order, False
