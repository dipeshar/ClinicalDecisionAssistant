"""Quote checks for synthetic decision support requiring human clinical sign-off.

Matching proves that words occur in a shown source, not that they support a claim.
"""

from collections.abc import Collection, Mapping
import re

from council.models import Citation, CitationDraft, Claim, ClaimDraft


def normalize_quote_text(text: str) -> str:
    """Normalization exclusively for quote comparison, never retrieval or storage.

    Fold case, collapse whitespace, and unify typographic single/double quotes
    and hyphen/dash styles. Other punctuation, digits and words remain intact.
    """
    styles = str.maketrans({
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "‐": "-", "‑": "-", "–": "-", "—": "-",
    })
    return " ".join(text.translate(styles).casefold().split())


def quote_failure(quote: str, passage: str) -> str | None:
    """Return a safe reason, or None; ellipsis parts must match without overlap.

    Count whitespace-separated words containing a letter or digit across all
    parts. Ellipses and standalone punctuation are not words. Leading/trailing
    ellipses may omit source text; no other wildcard or fuzzy matching is used.
    """
    normalized = normalize_quote_text(quote)
    source = normalize_quote_text(passage)
    parts = [part.strip() for part in normalized.split("...") if part.strip()]
    word_count = sum(any(char.isalnum() for char in word) for part in parts for word in part.split())
    if word_count < 4:
        return "quote has fewer than 4 words"
    if word_count > 40:
        return "quote has more than 40 words"
    cursor = 0
    for part in parts:
        # Do not accept a changed word just because it is a substring of another.
        left = r"(?<!\w)" if part[0].isalnum() or part[0] == "_" else ""
        right = r"(?!\w)" if part[-1].isalnum() or part[-1] == "_" else ""
        match = re.compile(left + re.escape(part) + right).search(source, cursor)
        if match is None:
            return "quote text not found in source in order"
        cursor = match.end()
    return None


def verify_citation(draft: CitationDraft, sources: Mapping[str, str],
                    shown_ids: Collection[str]) -> Citation:
    """Check against the code-owned source registry and this turn's shown IDs.

    Registry keys come from validated case sections/KB passages, never model
    output. Include carried-over KB IDs only when actually shown in this turn.
    Unknown non-CASE IDs are classified as KB candidates but cannot verify.
    """
    if draft.passage_id not in sources:
        reason = "unknown passage ID"
    elif draft.passage_id not in shown_ids:
        reason = "passage was not shown in this turn"
    else:
        reason = quote_failure(draft.quote, sources[draft.passage_id])
    return Citation(
        passage_id=draft.passage_id, quote=draft.quote,
        source_type="case" if draft.passage_id.startswith("CASE-") else "kb",
        verified=reason is None, verify_note=reason or "",
    )


def ground_claim(draft: ClaimDraft, claim_id: str, sources: Mapping[str, str],
                 shown_ids: Collection[str]) -> Claim:
    """Compute current checks; T10 owns the shared repair retry and final turn.

    Call again on repaired drafts. A claim needs at least one citation and every
    citation must pass. This function neither spends a retry nor fails a turn.
    """
    citations = [verify_citation(citation, sources, shown_ids) for citation in draft.citations]
    grounded = bool(citations) and all(citation.verified for citation in citations)
    return Claim(claim_id=claim_id, text=draft.text, citations=citations,
                 grounding_status="grounded" if grounded else "ungrounded")
