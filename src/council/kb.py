"""Synthetic KB retrieval for decision support requiring human clinical sign-off."""

from collections.abc import Mapping, Sequence
from pathlib import Path
import re
import warnings

from rank_bm25 import BM25Okapi

from council.models import Argument, CaseContext, Config, Passage, RetrievalResult, Role, Score
from council.privacy import scan_identifiers

KB_ROLES = frozenset({Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN, Role.RED})
TOP_K = 5


class KBError(ValueError):
    """The KB cannot safely be loaded or the retrieval inputs are inconsistent."""


class PassageLengthWarning(UserWarning):
    """A passage is outside the recommended 40 to 150 whitespace-separated words."""


def tokenize(text: str) -> list[str]:
    """One tokenizer for passages and queries: casefold, then alphanumeric words.

    No stemming, stop-word removal, embeddings, or special clinical vocabulary.
    Punctuation and underscores separate tokens; passage text is never changed.
    """
    return re.findall(r"[^\W_]+", text.casefold())


def safe_file_label(path: Path) -> str:
    """Keep error locations useful without echoing an identifier in a filename."""
    return "[redacted filename]" if scan_identifiers(str(path)) else str(path)


def read_passages(path: Path, role: Role, seen: set[str]) -> list[Passage]:
    label = safe_file_label(path)
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise KBError(f"cannot read UTF-8 KB file: {label}") from None
    lines = text.splitlines(keepends=True)
    titles = [line[2:].strip() for line in lines if line.startswith("# ")]
    headings = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    if not titles or not titles[0] or not headings:
        raise KBError(f"KB needs a source title and passage headings: {label}")
    passages: list[Passage] = []
    for position, (index, passage_id) in enumerate(headings):
        if not re.fullmatch(r"(?:SURG|PHYS|ANAES|ADMIN|RED)-KB-[0-9]{2}", passage_id):
            # A malformed heading may itself contain an identifier: never echo it.
            raise KBError(f"invalid passage ID: {label}")
        if passage_id in seen:
            raise KBError(f"duplicate passage ID: {label}: {passage_id}")
        if not passage_id.startswith(role.value + "-KB-"):
            raise KBError(f"wrong passage prefix: {label}: {passage_id}")
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "".join(lines[index + 1:end])
        # Titles travel with passages too. Scan both before emitting warnings.
        if scan_identifiers(body) or scan_identifiers(titles[0]):
            raise KBError(f"KB privacy rejection: {label}: {passage_id}")
        count = len(body.split())
        if not 40 <= count <= 150:
            warnings.warn(f"passage outside 40 to 150 words: {label}: {passage_id}",
                          PassageLengthWarning, stacklevel=2)
        seen.add(passage_id)
        passages.append(Passage(id=passage_id, kb=role.value, source_title=titles[0], text=body))
    return passages


def load_kb(folders: Mapping[Role, str | Path]) -> "KnowledgeBase":
    """Validate every file before returning any searchable KB; IDs are global."""
    seen: set[str] = set()
    by_role: dict[Role, list[Passage]] = {}
    for role in sorted(folders):
        if role not in KB_ROLES:
            raise KBError("only specialist and RED roles have a KB")
        folder = Path(folders[role])
        if not folder.is_dir():
            raise KBError(f"KB folder does not exist: {safe_file_label(folder)}")
        files = sorted(folder.rglob("*.md"))
        if not files:
            raise KBError(f"KB folder contains no Markdown files: {safe_file_label(folder)}")
        by_role[role] = [passage for path in files for passage in read_passages(path, role, seen)]
    return KnowledgeBase(by_role)


def build_query(role: Role, round: int, case: CaseContext, config: Config,
                arguments: Sequence[Argument] = (), scores: Sequence[Score] = ()) -> str:
    """Add peer summaries and judge-flagged own claim text only in Round 2."""
    if round not in (1, 2):
        raise KBError("retrieval supports only rounds 1 and 2")
    if role not in config.roles:
        raise KBError("retrieval role has no configured keywords")
    sections = {section.id: section.text for section in case.sections}
    parts = [" ".join(config.roles[role].keywords)]
    parts.extend(sections[id] for id in config.retrieval.case_sections if id in sections)
    if round == 2:
        previous = sorted((a for a in arguments if a.round == 1), key=lambda a: a.argument_id)
        parts.extend(a.summary for a in previous if a.role != role)
        own = [a for a in previous if a.role == role]
        if len(own) != 1 or own[0].status == "failed":
            raise KBError("Round 2 retrieval needs one successful own Round 1 argument")
        flagged: set[str] = set()
        for score in scores:
            if score.round == 1 and score.argument_id == own[0].argument_id:
                flagged.update(note.claim_id for note in score.untraceable_claims)
                flagged.update(note.claim_id for note in score.feedback if note.claim_id is not None)
        parts.extend(claim.text for claim in own[0].claims if claim.claim_id in flagged)
    return "\n".join(parts)


class KnowledgeBase:
    def __init__(self, by_role: Mapping[Role, Sequence[Passage]]) -> None:
        self.passages = {role: tuple(sorted(items, key=lambda p: p.id)) for role, items in by_role.items()}
        self.indices: dict[Role, BM25Okapi | None] = {}
        for role, passages in self.passages.items():
            corpus = [tokenize(p.text) for p in passages]
            self.indices[role] = BM25Okapi(corpus) if any(corpus) else None

    def retrieve(self, role: Role, round: int, query: str) -> RetrievalResult:
        if round not in (1, 2):
            raise KBError("retrieval supports only rounds 1 and 2")
        if role not in self.passages:
            raise KBError("role KB was not loaded")
        passages = self.passages[role]
        index = self.indices[role]
        scores = index.get_scores(tokenize(query)) if index is not None else [0.0] * len(passages)
        ranked = sorted(zip(passages, scores), key=lambda pair: (-float(pair[1]), pair[0].id))[:TOP_K]
        return RetrievalResult(role=role, round=round, query=query,
                               passages=[p for p, _ in ranked], scores=[float(score) for _, score in ranked])

    def round2_passages(self, result: RetrievalResult, own: Argument) -> list[Passage]:
        """Shown passages: retrieved top five plus previously cited own KB passages.

        Case sections are already available separately through CaseContext. Keep
        RetrievalResult's top-five scores intact; T12 can use this union in prompts.
        """
        if result.round != 2 or own.round != 1 or own.role != result.role or own.status == "failed":
            raise KBError("carryover needs a successful own Round 1 argument and Round 2 retrieval")
        available = {p.id: p for p in self.passages[result.role]}
        cited = {c.passage_id for claim in own.claims for c in claim.citations
                 if not c.passage_id.startswith("CASE-")}
        shown = {p.id: p for p in result.passages}
        # Failed citation checks can leave unknown IDs on ungrounded claims.
        # They name no available passage; leave the claim for later repair rather
        # than preventing its Round 2 turn or borrowing another role's evidence.
        for id in sorted(cited & available.keys()):
            shown.setdefault(id, available[id])
        return list(shown.values())
