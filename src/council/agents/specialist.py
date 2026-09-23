"""Specialist, Round 1 and Round 2: retrieval, the gateway call, parsing and grounding.

Round 1: build the retrieval query, retrieve the specialist's own knowledge
base passages, assemble the prompt, call the gateway, parse the response
against `ArgumentDraft`, and ground every claim's citations. A bad response
(invalid JSON, or any citation that fails) gets exactly one repair retry,
shared between the two kinds of problem (contracts section 13, rule 1). If
the repaired response still fails to parse, the turn is `failed` (contracts
rule 17); if only some citations still fail after repair, those claims stay
`ungrounded` and the argument still succeeds.

Round 2: shown the other three Round 1 arguments, its own Round 1 argument
with the code check results, and both judges' feedback/untraceable_claims
(never scores, per rule 14). Every Round 1 claim must be accounted for in
`revisions` exactly once (rule 13); a rebuttal must target a real Round 1
argument from a different role (rule 5); a Round 1 claim both judges flagged
cannot be kept (rule 24) — code overrides it after the repair rather than
failing the turn, the only outcome of these checks that doesn't either fail
the turn or stay silently as-is.
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
    Argument, ArgumentDraft, CaseContext, Claim, Config, GroundingStatus, Passage, Rebuttal,
    RetrievalResult, Revision, RevisionAction, Role, Round, Score, Step,
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
    gateway: LLMGateway, *, role: Role, step: Step, round_number: Round | None, body: str,
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


def claim_issues(claims: Sequence[Claim], label: str = "Claim") -> list[RepairIssue]:
    """Any already-grounded claim that came out ungrounded, named so a repair can fix it."""
    issues: list[RepairIssue] = []
    for claim in claims:
        if claim.grounding_status != GroundingStatus.UNGROUNDED:
            continue
        if not claim.citations:
            issues.append(RepairIssue(f"{label} {claim.claim_id}", "no citation was given"))
            continue
        for citation in claim.citations:
            if not citation.verified:
                issues.append(RepairIssue(f"{label} {claim.claim_id} citation to {citation.passage_id}",
                                          citation.verify_note))
    return issues


def citation_issues(draft: ArgumentDraft, argument_id: str, sources: Mapping[str, str],
                    shown_ids: Collection[str]) -> list[RepairIssue]:
    return claim_issues(ground_argument(draft, argument_id, sources, shown_ids))


def failed_argument(argument_id: str, role: Role, round_number: Round, retrieved_ids: Sequence[str],
                    repair_used: bool, failure_reason: str) -> Argument:
    return Argument(
        argument_id=argument_id, role=role, round=round_number, stance=None, summary="",
        claims=[], conditions=[], uncertainties=[], rebuttal=None, revisions=None,
        stance_changed=False, retrieved_passage_ids=list(retrieved_ids), repair_used=repair_used,
        status="failed", failure_reason=failure_reason,
    )


def run_round1(role: Role, case: CaseContext, kb: KnowledgeBase, config: Config, gateway: LLMGateway,
               prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
               retrieval_callback: Callable[[RetrievalResult], None] | None = None) -> Argument:
    """One specialist's Round 1 turn. Never raises for a bad model response; returns
    a `failed` Argument instead, per contracts rule 17."""
    argument_id = f"R1-{role.value}"
    query = build_query(role, 1, case, config)
    retrieval = kb.retrieve(role, 1, query)
    if retrieval_callback is not None:
        retrieval_callback(retrieval)
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


# ---------------------------------------------------------------------------
# Round 2
# ---------------------------------------------------------------------------

def render_other_arguments(others: Sequence[Argument]) -> str:
    """The other three Round 1 arguments (or as many as didn't fail), with grounding status."""
    if not others:
        return "(no other Round 1 arguments are available)"
    blocks = []
    for argument in sorted(others, key=lambda a: a.role.value):
        lines = [f"### {argument.argument_id} ({argument.role.value})",
                f"Stance: {argument.stance}", f"Summary: {argument.summary}", "Claims:"]
        for claim in argument.claims:
            lines.append(f"- [{claim.claim_id}] ({claim.grounding_status.value}) {claim.text}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_own_argument_with_checks(own: Argument) -> str:
    """The specialist's own Round 1 argument, with the code check result on each citation."""
    lines = [f"### {own.argument_id} (your Round 1 argument)", f"Stance: {own.stance}",
             f"Summary: {own.summary}", "Claims:"]
    for claim in own.claims:
        lines.append(f"- [{claim.claim_id}] {claim.text}")
        for citation in claim.citations:
            check = "verified" if citation.verified else f"check failed: {citation.verify_note}"
            lines.append(f"  - cites {citation.passage_id}: \"{citation.quote}\" ({check})")
    return "\n".join(lines)


def render_judge_notes(own_scores: Sequence[Score]) -> str:
    """Both judges' feedback and untraceable_claims on the specialist's own Round 1 argument,
    labeled by judge. Never the numeric scores (rule 14)."""
    if not own_scores:
        return "(no judge notes are available)"
    blocks = []
    for score in sorted(own_scores, key=lambda s: s.judge):
        lines = [f"### {score.judge}"]
        for claim in score.untraceable_claims:
            lines.append(f"- [{claim.claim_id}] untraceable: {claim.reason}")
        for note in score.feedback:
            target = f"[{note.claim_id}] " if note.claim_id else ""
            lines.append(f"- {target}{note.note}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def binding_claim_ids(own_scores: Sequence[Score]) -> set[str]:
    """Round 1 claim IDs both judges independently flagged (rule 24): a feedback note naming
    that claim, or listing it in untraceable_claims, in either combination."""
    by_judge: dict[str, set[str]] = {}
    for score in own_scores:
        flagged = {note.claim_id for note in score.feedback if note.claim_id is not None}
        flagged.update(claim.claim_id for claim in score.untraceable_claims)
        by_judge.setdefault(score.judge, set()).update(flagged)
    if len(by_judge) < 2:
        return set()
    judge_a, judge_b = list(by_judge.values())[:2]
    return judge_a & judge_b


def ground_round2(draft: ArgumentDraft, argument_id: str, sources: Mapping[str, str],
                  shown_ids: Collection[str]) -> tuple[list[Claim], Rebuttal | None]:
    """Ground the Round 2 claims list, then the rebuttal's response claims, continuing the
    same claim_id numbering (rule: rebuttal claims are grounded like any other claim)."""
    claims = ground_argument(draft, argument_id, sources, shown_ids)
    if draft.rebuttal is None:
        return claims, None
    start = len(claims) + 1
    response_claims = [ground_claim(claim_draft, f"{argument_id}-C{start + index}", sources, shown_ids)
                       for index, claim_draft in enumerate(draft.rebuttal.response_claims)]
    rebuttal = Rebuttal(
        target_argument_id=draft.rebuttal.target_argument_id, target_claim_id=draft.rebuttal.target_claim_id,
        why_strongest=draft.rebuttal.why_strongest, response_claims=response_claims,
    )
    return claims, rebuttal


def revision_structure_issues(draft: ArgumentDraft, own_round1: Argument) -> list[RepairIssue]:
    """Rule 13: every Round 1 claim of this specialist appears exactly once in revisions,
    kept/revised point at a real claim in the Round 2 claims list, and at least one claim
    is kept overall. These fail the turn if still wrong after the repair (unlike grounding)."""
    issues: list[RepairIssue] = []
    own_claim_ids = {claim.claim_id for claim in own_round1.claims}
    revisions = draft.revisions or []
    seen = [revision.round1_claim_id for revision in revisions]
    missing = own_claim_ids - set(seen)
    unknown = set(seen) - own_claim_ids
    duplicated = {claim_id for claim_id in seen if seen.count(claim_id) > 1}
    if missing:
        issues.append(RepairIssue("Revisions", f"missing a decision for: {', '.join(sorted(missing))}"))
    if unknown:
        issues.append(RepairIssue("Revisions",
                                  f"names a claim that isn't yours from Round 1: {', '.join(sorted(unknown))}"))
    if duplicated:
        issues.append(RepairIssue("Revisions",
                                  f"names the same Round 1 claim more than once: {', '.join(sorted(duplicated))}"))
    num_claims = len(draft.claims)
    for revision in revisions:
        if revision.action in (RevisionAction.KEPT, RevisionAction.REVISED):
            if revision.new_claim_index is None or not 1 <= revision.new_claim_index <= num_claims:
                issues.append(RepairIssue(f"Revision for {revision.round1_claim_id}",
                                          "new_claim_index does not point to a claim in your Round 2 claims list"))
    if not draft.claims:
        issues.append(RepairIssue("Claims", "you must keep at least one claim overall"))
    return issues


def binding_kept_issues(draft: ArgumentDraft, binding_ids: Collection[str]) -> list[RepairIssue]:
    """Rule 24: a claim both judges flagged cannot be marked kept."""
    return [RepairIssue(f"Revision for {revision.round1_claim_id}",
                        "both judges flagged this claim in Round 1; it cannot be kept, only revised or dropped")
            for revision in (draft.revisions or [])
            if revision.round1_claim_id in binding_ids and revision.action == RevisionAction.KEPT]


def rebuttal_issues(draft: ArgumentDraft, own_role: Role, round1_arguments: Sequence[Argument]) -> list[RepairIssue]:
    """Rule 5: the rebuttal targets a real Round 1 argument from a different role, and a
    claim that's actually inside it. A rebuttal is required every Round 2 turn."""
    if draft.rebuttal is None:
        return [RepairIssue("Rebuttal", "a rebuttal is required in Round 2")]
    by_id = {argument.argument_id: argument for argument in round1_arguments
             if argument.round == 1 and argument.status != "failed"}
    target = by_id.get(draft.rebuttal.target_argument_id)
    if target is None or target.role == own_role:
        return [RepairIssue("Rebuttal", "target_argument_id must be a real Round 1 argument from a different role")]
    if draft.rebuttal.target_claim_id not in {claim.claim_id for claim in target.claims}:
        return [RepairIssue("Rebuttal", "target_claim_id must be a claim inside the targeted argument")]
    return []


def apply_binding_overrides(
    revisions_draft: Sequence[Any], claims: Sequence[Claim], binding_ids: Collection[str],
    gateway: LLMGateway, role: Role, argument_id: str,
) -> tuple[list[Revision], list[Claim]]:
    """Rule 24's code override: a claim both judges flagged, still kept after the repair, is
    dropped by code — never left as a silent pass, and never a turn failure. Each override is
    recorded as its own trace validation event naming the claim id."""
    dropped_indices: set[int] = set()
    revisions: list[Revision] = []
    for revision in revisions_draft:
        if revision.round1_claim_id in binding_ids and revision.action == RevisionAction.KEPT:
            if revision.new_claim_index is not None:
                dropped_indices.add(revision.new_claim_index)
            gateway.write_validation_event(
                role=role, step=Step.SPECIALIST, round_number=2, parsed_ref=revision.round1_claim_id,
                note="both judges flagged this claim in Round 1; Round 2 kept it anyway, so code dropped it",
            )
            revisions.append(Revision(
                round1_claim_id=revision.round1_claim_id, action=RevisionAction.DROPPED, new_claim_index=None,
                reason="Both judges flagged this claim in Round 1; code dropped it.", new_claim_id=None,
            ))
        else:
            new_claim_id = f"{argument_id}-C{revision.new_claim_index}" if revision.new_claim_index is not None else None
            revisions.append(Revision(
                round1_claim_id=revision.round1_claim_id, action=revision.action,
                new_claim_index=revision.new_claim_index, reason=revision.reason, new_claim_id=new_claim_id,
            ))
    final_claims = [claim for index, claim in enumerate(claims, start=1) if index not in dropped_indices]
    return revisions, final_claims


def run_round2(role: Role, case: CaseContext, kb: KnowledgeBase, config: Config, gateway: LLMGateway,
              own_round1: Argument, round1_arguments: Sequence[Argument], round1_scores: Sequence[Score],
              prompts_dir: str | Path = prompting.DEFAULT_PROMPTS_DIR,
              retrieval_callback: Callable[[RetrievalResult], None] | None = None) -> Argument | None:
    """One specialist's Round 2 turn. Returns `None` when Round 1 itself failed (rule 16:
    a specialist whose Round 1 turn failed does not take part in Round 2). Never raises for
    a bad model response; returns a `failed` Argument instead, per contracts rule 17.
    """
    if own_round1.status == "failed":
        return None

    argument_id = f"R2-{role.value}"
    others = [argument for argument in round1_arguments
             if argument.round == 1 and argument.role != role and argument.status != "failed"]
    own_scores = [score for score in round1_scores
                 if score.round == 1 and score.argument_id == own_round1.argument_id]
    binding_ids = binding_claim_ids(own_scores)

    query = build_query(role, 2, case, config, arguments=round1_arguments, scores=round1_scores)
    retrieval = kb.retrieve(role, 2, query)
    if retrieval_callback is not None:
        retrieval_callback(retrieval)
    passages = kb.round2_passages(retrieval, own_round1)
    retrieved_ids = [passage.id for passage in passages]

    sources: dict[str, str] = {section.id: section.text for section in case.sections}
    sources.update({passage.id: passage.text for passage in passages})
    shown_ids = set(sources)

    data_blocks = [
        ("Case", render_case(case)),
        ("Other Round 1 arguments", render_other_arguments(others)),
        ("Your Round 1 argument", render_own_argument_with_checks(own_round1)),
        ("Judge notes on your Round 1 argument", render_judge_notes(own_scores)),
        ("Retrieved passages", render_passages(passages)),
    ]
    body = prompting.specialist_body(role, 2, data_blocks, prompts_dir)

    def find_issues(draft: ArgumentDraft) -> list[RepairIssue]:
        claims, rebuttal = ground_round2(draft, argument_id, sources, shown_ids)
        issues = claim_issues(claims)
        if rebuttal is not None:
            issues += claim_issues(rebuttal.response_claims, "Rebuttal claim")
        issues += revision_structure_issues(draft, own_round1)
        issues += binding_kept_issues(draft, binding_ids)
        issues += rebuttal_issues(draft, role, round1_arguments)
        return issues

    draft, repair_used, failure_reason, _model = call_and_parse_with_repair(
        gateway, role=role, step=Step.SPECIALIST, round_number=2, body=body, schema_model=ArgumentDraft,
        prompts_dir=prompts_dir, retrieved_ids=retrieved_ids, find_issues=find_issues,
    )

    if draft is None:
        return failed_argument(argument_id, role, 2, retrieved_ids, repair_used, failure_reason or "unknown failure")

    assert isinstance(draft, ArgumentDraft)
    hard_issues = revision_structure_issues(draft, own_round1) + rebuttal_issues(draft, role, round1_arguments)
    if hard_issues:
        # Still structurally wrong after the one repair retry: unlike an ungrounded claim,
        # this can't be left as-is, and unlike a binding "kept" claim, code has no safe fix.
        reasons = "; ".join(f"{issue.location}: {issue.reason}" for issue in hard_issues)
        return failed_argument(argument_id, role, 2, retrieved_ids, repair_used, reasons)

    claims, rebuttal = ground_round2(draft, argument_id, sources, shown_ids)
    revisions, final_claims = apply_binding_overrides(draft.revisions or [], claims, binding_ids,
                                                       gateway, role, argument_id)
    return Argument(
        argument_id=argument_id, role=role, round=2, stance=draft.stance, summary=draft.summary,
        claims=final_claims, conditions=draft.conditions, uncertainties=draft.uncertainties,
        rebuttal=rebuttal, revisions=revisions, stance_changed=draft.stance != own_round1.stance,
        retrieved_passage_ids=retrieved_ids, repair_used=repair_used, status="ok", failure_reason=None,
    )
