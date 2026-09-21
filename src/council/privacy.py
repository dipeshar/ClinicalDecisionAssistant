"""Identifier-format barriers for synthetic decision support requiring clinical sign-off.

These heuristics cannot identify free-text names or prove data is synthetic.
Only identifier kind and line number leave the scan; matched values never do.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from threading import Lock
from typing import Final
from uuid import uuid4

from council.models import EventType, Step, TraceEvent

# HUMAN REVIEW: the single identifier pattern list for ingest and the future gateway.
# National formats are shapes, not checksum validation: fake identifiers also block.
# Phone shapes include local seven-digit numbers; DOB needs a birth label. Ordinary dates, ages,
# blood pressure and decimal lab/dose values should not look like identifiers.
IDENTIFIER_PATTERNS: Final[dict[str, str]] = {
    "email": r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",
    "national_id": (
        r"(?<!\w)[A-Z]{5}[0-9]{4}[A-Z](?!\w)|"  # PAN-like
        r"(?<!\d)[0-9]{3}-[0-9]{2}-[0-9]{4}(?!\d)|"  # SSN-like
        r"(?<!\d)[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}(?!\d)"  # Aadhaar-like
    ),
    "phone": (
        r"(?<!\w)\+[1-9][0-9]{0,2}(?:[ ()-]*[0-9]){7,12}(?!\d)|"
        r"(?<![\w/-])[0-9]{3}-[0-9]{4}(?![\w/-])|"
        r"(?<![\w./-])(?:\+?[0-9]{1,3}[ -]?)?"
        r"(?:\([0-9]{3}\)[ -]?|[0-9]{3}[ -]?)[0-9]{3}[ -]?[0-9]{4}(?![\w./-])|"
        r"(?<![\w./-])(?:\+?[0-9]{1,3}[ -])?[0-9]{5}[ -][0-9]{5}(?![\w./-])"
    ),
    "long_number": r"(?<![\w.])[0-9]{8,}(?![\w.])",
    "date_of_birth": r"\b(?:date[ \t]+of[ \t]+birth|d\.?o\.?b\.?|born[ \t]+on)\b",
    "url": r"\b(?:https?://|ftp://|www\.)[^\s<>]+",
    "ip_address": (
        r"(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![\w.])|"
        r"(?<![\w:])(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}(?![\w:])|"
        r"(?<![\w:])(?=[0-9a-f:]*::)[0-9a-f]*:[0-9a-f:]+(?![\w:])"
    ),
    "id_label": (
        r"\b(?:patient[ \t]+(?:id|number)|id[ \t]*(?:number|no\.?|#)|"
        r"medical[ \t]+record(?:[ \t]+(?:number|no\.?))?|mrn|"
        r"aadhaar|aadhar|pan[ \t]*(?:number|no\.?|:)|ssn)\b|\bid[ \t]*:"
    ),
    "name_label": (
        r"\b(?:patient(?:['’]s)?[ \t]+name|name[ \t]+of[ \t]+(?:the[ \t]+)?patient)\b|"
        r"^[ \t>*-]*(?:full[ \t]+)?name[ \t]*:"
    ),
}


@dataclass(frozen=True)
class PrivacyHit:
    kind: str
    line_number: int


def scan_identifiers(text: str) -> list[PrivacyHit]:
    """Return safe findings in physical line order, never matched text."""
    hits: list[PrivacyHit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in IDENTIFIER_PATTERNS.items():
            if re.search(pattern, line, flags=re.IGNORECASE):
                hits.append(PrivacyHit(kind, number))
    return hits


def check_case_privacy(text: str, synthetic_marker: str) -> PrivacyHit | None:
    """Scan the whole file before any parsing; the marker must be in the preamble."""
    hits = scan_identifiers(text)
    if hits:
        return hits[0]
    preamble = text.splitlines()
    for index, line in enumerate(preamble):
        if line.startswith("##"):
            preamble = preamble[:index]
            break
    if not synthetic_marker.strip() or synthetic_marker.casefold() not in "\n".join(preamble).casefold():
        # A missing marker has no matched line. Point at the start of the preamble.
        return PrivacyHit("missing_marker", 1)
    return None


_REJECTION_LOCK = Lock()


def write_privacy_rejection(runs_dir: str | Path, hit: PrivacyHit) -> None:
    """Write one normal TraceEvent, with kind/line in error and no rejected data.

    Each rejection owns a new folder. No caller-supplied title, filename, or ID
    enters the run ID. This small writer does not implement T7's shared trace.
    """
    with _REJECTION_LOCK:
        now = datetime.now(timezone.utc)
        run_id = f"run-{now:%Y%m%d}-{now:%H%M%S}-rejected-{uuid4().hex}"
        event = TraceEvent(
            run_id=run_id, seq=1, timestamp=now.isoformat(), step=Step.INGEST,
            event_type=EventType.PRIVACY_BLOCK, role=None, round=None, model=None,
            prompt=None, retrieved_passage_ids=None, raw_output=None, parsed_ref=None,
            tokens_in=0, tokens_out=0, latency_ms=None, attempt=1, repair=False,
            budget_tokens_used=0, error=f"{hit.kind} at line {hit.line_number}",
        )
        try:
            folder = Path(runs_dir) / run_id
            folder.mkdir(parents=True, exist_ok=False)
            with (folder / "trace.jsonl").open("x", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
        except OSError:
            # Filesystem errors can include sensitive filenames; do not chain them.
            raise ValueError(f"privacy trace write failed: {hit.kind} at line {hit.line_number}") from None
