"""Specialist, Round 1: retrieval, the gateway call, parsing and grounding.

One specialist turn: build the retrieval query, retrieve the specialist's own
knowledge base passages, assemble the prompt, call the gateway, parse the
response against `ArgumentDraft`, and ground every claim's citations. A bad
response (invalid JSON, or any citation that fails) gets exactly one repair
retry, shared between the two kinds of problem (contracts section 13, rule
1). If the repaired response still fails to parse, the turn is `failed`
(contracts rule 17); if only some citations still fail after repair, those
claims stay `ungrounded` and the argument still succeeds.
"""

from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from council.agents import prompting
from council.agents.prompting import RepairIssue, SchemaSource
from council.gateway import GatewayRefusal, LLMGateway
from council.grounding import ground_claim
from council.kb import KnowledgeBase, build_query
from council.models import (
    Argument, ArgumentDraft, CaseContext, Claim, Config, GroundingStatus, Passage, Role, Round, Step,
)


def render_case(case: CaseContext) -> str:
    """Every section, in order, labeled with its heading and ID for citing."""
    return "\n\n".join(f"## {section.heading} ({section.id})\n{section.text}" for section in case.sections)


def render_passages(passages: Sequence[Passage]) -> str:
    """Every retrieved passage, labeled with its ID and source title for citing."""
    if not passages:
        return "(no passages were retrieved)"
    return "\n\n".join(f"## {passage.id} — {passage.source_title}\n{passage.text}" for passage in passages)


def describe_validation_error(error: ValidationError) -> str:
    """A short, readable summary: one field and reason per error, semicolon-joined."""
    parts = [f"{'.'.join(str(p) for p in item['loc']) or '(top level)'}: {item['msg']}"
             for item in error.errors(include_url=False, include_context=False, include_input=False)]
    return "; ".join(parts) if parts else str(error)


def parse_draft(raw_output: str, schema_source: SchemaSource) -> tuple[Any | None, str | None]:
    """Bad JSON is not the gateway's job (T8); this is where it's actually checked.

    `schema_source` is either a draft model class (one object) or a `TypeAdapter`
    (for example `list[ScoreDraft]`, T11's judge response), the same distinction
    `prompting.schema_block` already makes for the schema appended to the prompt.
    """
    try:
        if isinstance(schema_source, type):
            return schema_source.model_validate_json(raw_output), None
        return schema_source.validate_json(raw_output), None
    except ValidationError as error:
        return None, describe_validation_error(error)


def ground_argument(draft: ArgumentDraft, argument_id: str, sources: Mapping[str, str],
                    shown_ids: Collection[str]) -> list[Claim]:
    return [ground_claim(claim, f"{argument_id}-C{index}", sources, shown_ids)
            for index, claim in enumerate(draft.claims, start=1)]


def call_and_parse_with_repair(
    gateway: LLMGateway, *, role: Role, step: Step, round_number: Round, body: str,
    schema_model: SchemaSource, prompts_dir: str | Path, retrieved_ids: Sequence[str],
    find_issues: Callable[[Any], list[RepairIssue]],
) -> tuple[Any | None, bool, str | None, str | None]:
    """One gateway call, parsed against `schema_model` (a draft model class, or a
    `TypeAdapter` such as `list[ScoreDraft]` for T11's judge response).

    If parsing fails, or `find_issues(draft)` reports any problem with an
    otherwise-valid draft, one repair retry follows (rule 1: bad JSON and
    bad citations share the same single retry). Returns
    (final draft or None, repair_used, failure_reason, model_label). `model_label`
    is the gateway's `provider/model` string for whichever call actually produced
    the returned draft (None if no draft was produced), for CODE-owned fields
    like `Score.model` that record which model scored.
    """
    prompt = prompting.render(body, schema_model)
    try:
        result = gateway.call(role=role, step=step, round_number=round_number, prompt=prompt,
                              retrieved_passage_ids=list(retrieved_ids))
    except GatewayRefusal as error:
        return None, False, f"gateway refused the call: {error}", None

    draft, parse_error = parse_draft(result.raw_output, schema_model)
    issues = find_issues(draft) if draft is not None else []
    if draft is not None and not issues:
        return draft, False, None, result.model

    repair_issues = issues if draft is not None else [
        RepairIssue("Response", parse_error or "could not parse as JSON matching the schema"),
    ]
    repair_text = prompting.repair_prompt(body, repair_issues, schema_model, prompts_dir)
    try:
        repaired = gateway.call(role=role, step=step, round_number=round_number, prompt=repair_text,
                                repair=True, retrieved_passage_ids=list(retrieved_ids))
    except GatewayRefusal as error:
        return None, True, f"gateway refused the repair attempt: {error}", None

    repaired_draft, repaired_error = parse_draft(repaired.raw_output, schema_model)
    if repaired_draft is None:
        return None, True, repaired_error or "repaired response still did not parse", None
    return repaired_draft, True, None, repaired.model


def citation_issues(draft: ArgumentDraft, argument_id: str, sources: Mapping[str, str],
                    shown_ids: Collection[str]) -> list[RepairIssue]:
    issues: list[RepairIssue] = []
    for claim in ground_argument(draft, argument_id, sources, shown_ids):
        if claim.grounding_status != GroundingStatus.UNGROUNDED:
            continue
        if not claim.citations:
            issues.append(RepairIssue(f"Claim {claim.claim_id}", "no citation was given"))
            continue
        for citation in claim.citations:
            if not citation.verified:
                issues.append(RepairIssue(f"Claim {claim.claim_id} citation to {citation.passage_id}",
                                          citation.verify_note))
    return issues


def failed_argument(argument_id: str, role: Role, round_number: Round, retrieved_ids: Sequence[str],
                    repair_used: bool, failure_reason: str) -> Argument:
    return Argument(
        argument_id=argument_id, role=role, round=round_number, stance=None, summary="",
        claims=[], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
        stance_changed=False, retrieved_passage_ids=list(retrieved_ids), repair_used=repair_used,
        status="failed", failure_reason=failure_reason,
    )


def run_round1(role: Role, case: CaseContext, kb: KnowledgeBase, config: Config, gateway: LLMGateway,
               prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR) -> Argument:
    """One specialist's Round 1 turn. Never raises for a bad model response; returns
    a `failed` Argument instead, per contracts rule 17."""
    argument_id = f"R1-{role.value}"
    query = build_query(role, 1, case, config)
    retrieval = kb.retrieve(role, 1, query)
    retrieved_ids = [passage.id for passage in retrieval.passages]

    sources: dict[str, str] = {section.id: section.text for section in case.sections}
    sources.update({passage.id: passage.text for passage in retrieval.passages})
    shown_ids = set(sources)

    data_blocks = [("Case", render_case(case)), ("Retrieved passages", render_passages(retrieval.passages))]
    body = prompting.specialist_body(role, 1, data_blocks, prompts_dir)

    draft, repair_used, failure_reason, _model = call_and_parse_with_repair(
        gateway, role=role, step=Step.SPECIALIST, round_number=1, body=body, schema_model=ArgumentDraft,
        prompts_dir=prompts_dir, retrieved_ids=retrieved_ids,
        find_issues=lambda d: citation_issues(d, argument_id, sources, shown_ids),
    )

    if draft is None:
        return failed_argument(argument_id, role, 1, retrieved_ids, repair_used, failure_reason or "unknown failure")

    assert isinstance(draft, ArgumentDraft)  # narrows the shared helper's BaseModel return for the type checker
    claims = ground_argument(draft, argument_id, sources, shown_ids)
    return Argument(
        argument_id=argument_id, role=role, round=1, stance=draft.stance, summary=draft.summary,
        claims=claims, conditions=draft.conditions, uncertainties=draft.uncertainties,
        rebuttal=None, revisions=None, stance_changed=False, retrieved_passage_ids=retrieved_ids,
        repair_used=repair_used, status="ok", failure_reason=None,
    )
