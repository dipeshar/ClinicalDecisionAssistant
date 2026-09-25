"""Heuristic injection scan for synthetic decision support requiring clinical sign-off.

This detects suspicious text, not intent or clinical correctness. It is not a
complete injection defense; prompt delimiters and human review remain required.
"""

from bisect import bisect_right
from collections.abc import Mapping
import re
from typing import Final

from council.models import InjectionFlag

FLAG_TAG: Final = "[FLAGGED: possible instruction]"

# HUMAN REVIEW: all scanner patterns live here, in four named groups.
# Require instruction/prompt targets or council-output language, not ordinary
# verbs such as recommend, proceed, stop, withhold, take, or administer.
SCANNER_PATTERNS: Final[dict[str, str]] = {
    "instruction_override": (
        r"\b(?:ignore|disregard|override|forget)\s+"
        r"(?:(?:all|any|the|your|these|those)\s+)*"
        r"(?:above\b|(?:previous|prior|earlier)\s+(?:instructions?|prompts?|rules?)\b|"
        r"(?:system|developer|AI|council)\s+(?:instructions?|prompts?|rules?)\b)"
    ),
    "role_spoofing": (
        r"\byou\s+are\s+now\s+(?:(?:a|an|the)\s+)?"
        r"(?:AI|assistant|system|developer|chair|judge|council|surgeon)\b|"
        r"^[ \t>#*`]*(?:system|developer|assistant)\s*:|"
        r"\[/?(?:SYSTEM|INST)\]|<\|(?:im_start|system|assistant)\|>|"
        r"</?(?:system|developer|assistant)>"
    ),
    "answer_manipulation": (
        r"\b(?:score|rate|grade|give)\s+"
        r"(?:this(?:\s+(?:argument|answer|response))?|(?:the\s+)?(?:argument|answer|response))\s+"
        r"(?:(?:as|a|at|with)\s+)*(?:[1-5](?:/5)?|five|maximum|highest)\b|"
        r"\b(?:do\s+not|don['’]t|never)\s+(?:mention|discuss|report|disclose|include)\b"
        r"[^\r\n.!?]{0,100}\b(?:kidney|renal|results?|findings?|risks?|evidence|uncertainties|complications?)\b|"
        r"\b(?:hide|omit|suppress|conceal)\b[^\r\n.!?]{0,60}\b(?:results?|findings?|evidence|risks?)\b|"
        r"\b(?:AI|assistant|council|chair|judges?)\s*[:,]?\s+(?:must|shall|should)\s+"
        r"(?:always\s+)?(?:approve|recommend|output|return|score)\b|"
        r"\b(?:output|return)\s+(?:only\s+)?(?:APPROVED|proceed|decline)\b"
    ),
    "hidden_text": (
        r"<!--[\s\S]*?(?:-->|\Z)|"
        r"<(?:span|div|p)\b[^>]*(?:\bhidden\b|display\s*:\s*none|"
        r"visibility\s*:\s*hidden|opacity\s*:\s*0\b|font-size\s*:\s*0\b)"
        r"[^>]*>[\s\S]*?(?:</(?:span|div|p)\s*>|\Z)|"
        r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]|"
        r"&#(?:x(?:200[b-f]|202[a-e]|206[0-f]|feff)|820[3-7]|823[4-8]|8288);"
    ),
}


def scan_section(section_id: str, text: str, *, start_line: int = 1) -> tuple[str, list[InjectionFlag]]:
    """Tag matched lines without deleting text; numbers refer to original file lines.

    A line receives one flag per matching group and just one added tag. Matching
    spans may cross lines (including comments and split override instructions).
    """
    if start_line < 1:
        raise ValueError("start_line must be a one-based line number")
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    matched: dict[int, list[str]] = {}
    for name, pattern in SCANNER_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            first = bisect_right(offsets, match.start()) - 1
            last = bisect_right(offsets, match.end() - 1) - 1
            for index in range(first, last + 1):
                reasons = matched.setdefault(index, [])
                if name not in reasons:
                    reasons.append(name)
    flags: list[InjectionFlag] = []
    for index in sorted(matched):
        for name in matched[index]:
            flags.append(InjectionFlag(section_id=section_id, line_number=start_line + index,
                                       matched_pattern=name))
        lines[index] = FLAG_TAG + " " + lines[index]
    return "".join(lines), flags


def matched_categories(text: str) -> list[str]:
    """Which SCANNER_PATTERNS categories match at least once anywhere in text,
    in SCANNER_PATTERNS order. Whole-text, not line-by-line (contracts rule 29:
    the gateway scores one combined system+user string, not individual lines)."""
    return [name for name, pattern in SCANNER_PATTERNS.items()
            if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)]


def score_text(text: str, weights: Mapping[str, int]) -> tuple[int, list[str]]:
    """Total weighted injection score for text, and which categories fired.

    A category that matches contributes its configured weight once, no matter
    how many times it matches. `weights` is config-driven (contracts section 11,
    `injection_scoring.weights`); this function has no opinion on the numbers.
    Purely additive: `scan_section`'s own per-line flagging for ingest is
    untouched and unaffected by this function's existence.
    """
    matched = matched_categories(text)
    return sum(weights[name] for name in matched), matched
