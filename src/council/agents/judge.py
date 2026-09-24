"""Judges: one provider call per non-failed argument, per judge.

Each call contains one argument and its uniquely cited sources, parses one
`ScoreDraft`, and verifies that its `argument_id` matches the argument sent.
The shared repair retry applies to bad shape and mismatched IDs. Round 1
feedback is truncated to configured limits; Round 2 feedback is forced empty
and requires a counterarguments score (contracts section 6).
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

from council.agents import prompting
from council.agents.prompting import RepairIssue
from council.agents.specialist import call_and_parse_with_repair, render_case
from council.gateway import LLMGateway
from council.models import Argument, CaseContext, Claim, Config, Round, Score, ScoreDraft, Step, Role

def argument_claims(argument: Argument) -> list[Claim]:
    """Return main and rebuttal-response claims in their displayed order."""
    response_claims = argument.rebuttal.response_claims if argument.rebuttal is not None else []
    return [*argument.claims, *response_claims]


def cited_passage_ids(arguments: Sequence[Argument]) -> list[str]:
    """Return cited source IDs once each, preserving their first displayed use."""
    return list(dict.fromkeys(
        citation.passage_id
        for argument in arguments
        for claim in argument_claims(argument)
        for citation in claim.citations
    ))


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
    return "\n\n".join(
        f"### {passage_id}\n{sources.get(passage_id, '(source not available)')}"
        for passage_id in cited_passage_ids(arguments)
    )


def truncate_feedback(feedback: Sequence[dict], max_notes: int, max_words: int) -> list[dict]:
    """Extra notes beyond `max_notes` are cut; each kept note's text is cut to
    `max_words` words (contracts section 11 config: "Extra notes are cut by code")."""
    kept = list(feedback)[:max_notes]
    return [{"claim_id": note["claim_id"], "note": " ".join(note["note"].split()[:max_words])} for note in kept]


def build_score(judge: Role, model: str, round_number: Round, draft: ScoreDraft, config: Config) -> Score:
    """Force the round-dependent fields (contracts section 6) rather than trust the
    model: Round 1 never has a counterarguments score, Round 2 never has feedback.

    `draft.argument_id` is used as-is after `run_judge` verifies that it matches
    the one argument sent (rule 25).
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
    judge: Role, argument: Argument, case: CaseContext,
    passage_sources: Mapping[str, str], config: Config, gateway: LLMGateway,
    prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
) -> tuple[Score | None, bool]:
    """Score one non-failed argument. Return (score, failed)."""
    if argument.status == "failed":
        raise ValueError("a failed argument must not be sent to a judge")
    round_number = argument.round
    shown = [argument]

    sources: dict[str, str] = {section.id: section.text for section in case.sections}
    sources.update(passage_sources)

    cited_ids = set(cited_passage_ids(shown))
    uncited_case = case.model_copy(update={
        "sections": [section for section in case.sections if section.id not in cited_ids],
    })
    data_blocks = [
        ("Case sections not repeated below", render_case(uncited_case)),
        ("Cited sources", render_shared_sources(shown, sources)),
        (argument.argument_id, render_argument(argument)),
    ]
    body = prompting.judge_body(data_blocks, prompts_dir)

    def find_issues(score: ScoreDraft) -> list[RepairIssue]:
        if score.argument_id != argument.argument_id:
            return [RepairIssue(
                "argument_id",
                f"must match the one argument shown: {argument.argument_id}",
            )]
        if round_number == 2 and score.counterarguments is None:
            return [RepairIssue(
                f"Score for {score.argument_id}",
                "counterarguments score is required in Round 2",
            )]
        return []

    draft, _repair_used, failure_reason, model = call_and_parse_with_repair(
        gateway, role=judge, step=Step.JUDGE, round_number=round_number, body=body,
        schema_model=ScoreDraft, prompts_dir=prompts_dir, retrieved_ids=[], find_issues=find_issues,
    )

    if draft is None:
        assert failure_reason is not None
        return None, True
    if find_issues(draft):
        return None, True

    assert model is not None
    return build_score(judge, model, round_number, draft, config), False
