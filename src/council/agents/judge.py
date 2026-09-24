"""Judges: one call per judge per round, scoring every non-failed argument at once.

One judge call: skip failed arguments, shuffle the non-failed arguments of
the round (recording the shuffled order, to reduce position bias per
design.md), assemble the prompt with each argument's cited passages shown in
full, call the gateway, parse the response as one `ScoreDraft` per argument
(rule 1's shared repair retry applies here too), and turn each into a
CODE-owned `Score`. Round 1 feedback is truncated to the configured limits;
Round 2 feedback is always empty, and Round 2 always needs a counterarguments
score, regardless of what the model wrote for either (contracts section 6).

Scores are matched to arguments by the `argument_id` each `ScoreDraft` names,
never by array position (contracts section 6, rule 25): a response naming
anything other than exactly the set of arguments shown — missing, duplicate,
or unknown — is a validation failure. If it is still wrong after the one
repair retry, the whole call is treated as failed (rule 18), the same as bad
JSON that never parses; the run continues with the other judge.
"""

from collections.abc import Callable, Mapping, MutableSequence, Sequence
from pathlib import Path
import random

from pydantic import TypeAdapter

from council.agents import prompting
from council.agents.prompting import RepairIssue
from council.agents.specialist import call_and_parse_with_repair, render_case
from council.gateway import LLMGateway
from council.models import Argument, CaseContext, Claim, Config, Round, Score, ScoreDraft, Step, Role

JUDGE_SCHEMA: TypeAdapter[list[ScoreDraft]] = TypeAdapter(list[ScoreDraft])


def argument_claims(argument: Argument) -> list[Claim]:
    """Return main and rebuttal-response claims in their displayed order."""
    response_claims = argument.rebuttal.response_claims if argument.rebuttal is not None else []
    return [*argument.claims, *response_claims]


def render_argument(argument: Argument) -> str:
    """Render argument content with citation IDs and quotes, but no repeated sources."""
    lines = [f"### {argument.argument_id} ({argument.role.value}, round {argument.round})",
             f"Stance: {argument.stance}", f"Summary: {argument.summary}", "", "Claims:"]
    for claim in argument.claims:
        lines.append(f"- [{claim.claim_id}] {claim.text}")
        for citation in claim.citations:
            lines.append(f"  - cites {citation.passage_id}: \"{citation.quote}\"")
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
            for citation in claim.citations:
                lines.append(f"  - cites {citation.passage_id}: \"{citation.quote}\"")
    return "\n".join(lines)


def render_shared_sources(arguments: Sequence[Argument], sources: Mapping[str, str]) -> str:
    """Render every source cited across the shown arguments exactly once."""
    passage_ids = dict.fromkeys(
        citation.passage_id
        for argument in arguments
        for claim in argument_claims(argument)
        for citation in claim.citations
    )
    return "\n\n".join(
        f"### {passage_id}\n{sources.get(passage_id, '(source not available)')}"
        for passage_id in passage_ids
    )


def truncate_feedback(feedback: Sequence[dict], max_notes: int, max_words: int) -> list[dict]:
    """Extra notes beyond `max_notes` are cut; each kept note's text is cut to
    `max_words` words (contracts section 11 config: "Extra notes are cut by code")."""
    kept = list(feedback)[:max_notes]
    return [{"claim_id": note["claim_id"], "note": " ".join(note["note"].split()[:max_words])} for note in kept]


def build_score(judge: Role, model: str, round_number: Round, draft: ScoreDraft, config: Config) -> Score:
    """Force the round-dependent fields (contracts section 6) rather than trust the
    model: Round 1 never has a counterarguments score, Round 2 never has feedback.

    `draft.argument_id` is used as-is: by the time this is called, `run_judge`
    has already verified the full set of argument_ids in the response exactly
    matches the arguments shown (rule 25).
    """
    counterarguments = None if round_number == 1 else draft.counterarguments
    feedback = [] if round_number == 2 else truncate_feedback(
        [note.model_dump() for note in draft.feedback], config.judging.feedback_max_notes,
        config.judging.feedback_max_words,
    )
    return Score(
        judge=judge, argument_id=draft.argument_id, model=model, round=round_number,
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

    data_blocks = [("Case", render_case(case)), ("Cited sources", render_shared_sources(shown, sources))]
    data_blocks.extend((argument.argument_id, render_argument(argument)) for argument in shown)
    body = prompting.judge_body(data_blocks, prompts_dir)

    expected_ids = {argument.argument_id for argument in shown}

    def find_issues(scores: list[ScoreDraft]) -> list[RepairIssue]:
        seen_ids = [score.argument_id for score in scores]
        missing = expected_ids - set(seen_ids)
        unknown = sorted(set(seen_ids) - expected_ids)
        duplicated = sorted({id for id in seen_ids if seen_ids.count(id) > 1})
        issues = []
        if missing:
            issues.append(RepairIssue("Response", f"missing a score for: {', '.join(sorted(missing))}"))
        if unknown:
            issues.append(RepairIssue("Response", f"scored an argument that was not shown: {', '.join(unknown)}"))
        if duplicated:
            issues.append(RepairIssue("Response", f"scored more than once: {', '.join(duplicated)}"))
        if issues:
            # The argument_id set is wrong; positions can't be trusted yet, so
            # don't also report per-score problems until this is fixed.
            return issues
        if round_number == 2:
            return [RepairIssue(f"Score for {score.argument_id}",
                                "counterarguments score is required in Round 2")
                    for score in scores if score.counterarguments is None]
        return []

    draft, _repair_used, failure_reason, model = call_and_parse_with_repair(
        gateway, role=judge, step=Step.JUDGE, round_number=round_number, body=body,
        schema_model=JUDGE_SCHEMA, prompts_dir=prompts_dir, retrieved_ids=[], find_issues=find_issues,
    )

    if draft is None:
        assert failure_reason is not None  # call_and_parse_with_repair always explains a None draft
        return [], [], True

    if find_issues(draft):
        # Still wrong after the one repair retry (rule 25): the call is failed,
        # not partially accepted, since positions can't be trusted to fall back on.
        return [], [], True

    assert model is not None  # a successful draft always came from a real gateway call
    by_id = {score.argument_id: score for score in draft}
    scores = [build_score(judge, model, round_number, by_id[argument.argument_id], config) for argument in shown]
    return scores, presented_order, False
