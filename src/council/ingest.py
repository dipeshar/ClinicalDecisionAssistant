"""Parse synthetic cases for decision support requiring human clinical sign-off."""

from hashlib import sha256
from pathlib import Path
from typing import Final

from council.models import CaseContext, CaseSection, InjectionFlag
from council.scanner import scan_section

CASE_HEADINGS: Final[dict[str, str]] = {
    "Patient Profile": "CASE-profile",
    "Diagnoses and History": "CASE-diagnoses",
    "Comorbidities": "CASE-comorbidities",
    "Medications": "CASE-medications",
    "Allergies": "CASE-allergies",
    "Tests and Imaging": "CASE-tests",
    "Proposed Procedure": "CASE-procedure",
    "Consultant Review": "CASE-consultant-review",
}


class IngestError(ValueError):
    """The case cannot be read or does not follow the supported template."""


def find_headings(lines: list[str]) -> list[tuple[int, str]]:
    """Recognize the template's headings, allowing missing but not ambiguous ones."""
    headings: list[tuple[int, str]] = []
    seen: set[str] = set()
    order = list(CASE_HEADINGS)
    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        if heading not in CASE_HEADINGS:
            raise IngestError(f"unknown section heading at line {index + 1}: {heading}")
        if heading in seen:
            raise IngestError(f"duplicate section heading at line {index + 1}: {heading}")
        if headings and order.index(heading) < order.index(headings[-1][1]):
            raise IngestError(f"section headings are out of template order at line {index + 1}")
        seen.add(heading)
        headings.append((index, heading))
    return headings


def read_title(preamble: str) -> str:
    """Reject suspicious uncitable text, as authorized by the human for T3."""
    _, flags = scan_section("", preamble)
    if flags:
        first = flags[0]
        raise IngestError(f"suspicious title/preamble at line {first.line_number}: {first.matched_pattern}")
    first_line = next((line.strip() for line in preamble.splitlines() if line.strip()), "")
    if not first_line.startswith("# Case:") or not first_line.removeprefix("# Case:").strip():
        raise IngestError("case must begin with a nonempty '# Case: title' heading")
    return first_line.removeprefix("# Case:").strip()


def ingest_case(path: str | Path) -> CaseContext:
    """Read once; hash original bytes; preserve section text except warning tags.

    case_id is the filename stem. Flag line numbers are one-based positions in
    the original file, including title, preamble and blank lines. No model runs.
    """
    source = Path(path)
    try:
        raw = source.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise IngestError(f"cannot read UTF-8 case file: {source}") from error
    lines = text.splitlines(keepends=True)
    headings = find_headings(lines)
    preamble_end = headings[0][0] if headings else len(lines)
    title = read_title("".join(lines[:preamble_end]))
    sections: list[CaseSection] = []
    flags: list[InjectionFlag] = []
    for position, (index, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        section_id = CASE_HEADINGS[heading]
        body = "".join(lines[index + 1:end])
        tagged, section_flags = scan_section(section_id, body, start_line=index + 2)
        sections.append(CaseSection(
            id=section_id, heading=heading, text=tagged, flagged=bool(section_flags),
            flag_reasons=list(dict.fromkeys(flag.matched_pattern for flag in section_flags)),
        ))
        flags.extend(section_flags)
    present = {heading for _, heading in headings}
    return CaseContext(
        case_id=source.stem, source_file=str(source), case_hash=sha256(raw).hexdigest(), title=title,
        sections=sections, missing_sections=[heading for heading in CASE_HEADINGS if heading not in present],
        injection_flags=flags,
    )
