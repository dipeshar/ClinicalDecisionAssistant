"""Only fabricated identifier strings; nothing here is real patient data."""

import json
from pathlib import Path
import traceback

import pytest

from council.ingest import IngestError, ingest_case
from council.models import Config, TraceEvent
from council.privacy import IDENTIFIER_PATTERNS, PrivacyHit, scan_identifiers


@pytest.mark.parametrize("kind,value", [
    ("email", "fictional.patient@example.invalid"),
    ("phone", "+1 (202) 555-0100"),
    ("phone", "202-555-0100"),
    ("phone", "+91 99999 00000"),
    ("phone", "9999900000"),
    ("phone", "+44 20 7946 0958"),
    ("phone", "555-0100"),
    ("national_id", "9999 0000 1111"),
    ("national_id", "9999-0000-1111"),
    ("national_id", "999900001111"),
    ("national_id", "ZZZZZ0000Z"),
    ("national_id", "999-00-0000"),
    ("long_number", "12345678901234567890"),
    ("date_of_birth", "Date of birth: 01/01/1900"),
    ("date_of_birth", "DOB: 1900-01-01"),
    ("date_of_birth", "Born on 1 January 1900"),
    ("url", "https://example.invalid/patient"),
    ("url", "www.example.invalid"),
    ("ip_address", "192.0.2.1"),
    ("ip_address", "2001:db8::1"),
    ("id_label", "ID number: FICTIONAL"),
    ("id_label", "Patient ID: DEMO"),
    ("id_label", "MRN: DEMO"),
    ("id_label", "ID: DEMO"),
    ("name_label", "Patient name: Fictional Example"),
    ("name_label", "Name of the patient: Fictional Example"),
    ("name_label", "Name: Fictional Example"),
])
def test_identifier_kinds(kind: str, value: str) -> None:
    hits = scan_identifiers("Normal clinical text.\r\n" + value)
    assert PrivacyHit(kind, 2) in hits
    assert value not in repr(hits)
    assert all(set(vars(hit)) == {"kind", "line_number"} for hit in hits)
    assert scan_identifiers(value.swapcase())


@pytest.mark.parametrize("text", [
    "The patient is 64 years old, BMI 25.2 kg/m2, blood pressure 150/90 mmHg.",
    "Sodium 140 mmol/L, creatinine 1.2 mg/dL, haemoglobin 12.5 g/dL. eGFR 45.",
    "Metoprolol 25 mg twice daily. Insulin 10 units. Infusion 1000 mL over 8 hours.",
    "Tests performed 2026-09-21. Review on 21/09/2026 or 21 September 2026.",
    "Review at 10:30:00. Range 120-150. SpO2 98%. Heart rate 70/min.",
    "The patient has no known allergies. I recommend proceeding with surgery.",
    "R1-SURG-C1 cites CASE-tests and ANAES-KB-04. Age 60-65, surgery in 2026.",
])
def test_clinical_values_are_not_identifiers(text: str) -> None:
    assert scan_identifiers(text) == []


def test_pattern_list_is_complete() -> None:
    assert set(IDENTIFIER_PATTERNS) == {
        "email", "phone", "national_id", "long_number", "date_of_birth",
        "url", "ip_address", "id_label", "name_label",
    }


def case_text(marker: str) -> str:
    return ("# Case: Synthetic privacy test\n\n> " + marker +
            ". Decision support requires human clinical sign-off.\n\n"
            "## Patient Profile\nThe patient is 64 years old.\n"
            "## Tests and Imaging\nBlood pressure 150/90. Creatinine 1.2 mg/dL.\n"
            "Review on 21/09/2026.\n")


def rejection_trace(config: Config) -> tuple[Path, dict[str, object]]:
    folders = list(Path(config.paths.runs).iterdir())
    assert len(folders) == 1
    files = list(folders[0].iterdir())
    assert [p.name for p in files] == ["trace.jsonl"]
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    event = TraceEvent.model_validate(record)
    assert event.event_type == "privacy_block" and event.step == "ingest"
    assert event.seq == 1 and event.run_id == folders[0].name
    assert event.tokens_in == event.tokens_out == event.budget_tokens_used == 0
    for field in ("prompt", "raw_output", "model", "role", "round", "parsed_ref", "retrieved_passage_ids"):
        assert record[field] is None
    return files[0], record


def test_normal_case_and_case_insensitive_marker(tmp_path: Path, config: Config) -> None:
    path = tmp_path / "normal.md"
    path.write_bytes(case_text(config.privacy.synthetic_marker.swapcase()).encode())
    context = ingest_case(path, config)
    assert context.sections[0].text == "The patient is 64 years old.\n"
    assert context.injection_flags == []
    assert not Path(config.paths.runs).exists()


@pytest.mark.parametrize("location", ["title", "preamble", "heading", "section", "comment"])
def test_rejects_identifiers_everywhere_before_parsing(
    tmp_path: Path, config: Config, location: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from council import ingest
    value = "fictional.patient@example.invalid"
    text = case_text(config.privacy.synthetic_marker)
    if location == "title":
        text = text.replace("Synthetic privacy test", value)
    elif location == "preamble":
        text = text.replace("\n\n>", "\n" + value + "\n>")
    elif location == "heading":
        text = text.replace("## Patient Profile", "## " + value)
    elif location == "comment":
        text += "<!-- " + value + " -->\n"
    else:
        text += value + "\n"
    path = tmp_path / (value + ".md")  # Even a sensitive filename must not reach outputs.
    path.write_text(text, encoding="utf-8")
    line = next(i for i, row in enumerate(text.splitlines(), 1) if value in row)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("privacy must run before template parsing or CaseContext construction")

    monkeypatch.setattr(ingest, "find_headings", forbidden)
    monkeypatch.setattr(ingest, "CaseContext", forbidden)
    with pytest.raises(IngestError) as caught:
        ingest_case(path, config)
    assert str(caught.value) == f"email at line {line}"
    trace, record = rejection_trace(config)
    assert record["error"] == f"email at line {line}"
    output = trace.read_text(encoding="utf-8") + str(caught.value) + repr(caught.value)
    assert value not in output and text not in output
    assert "The patient" not in output
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("where", ["absent", "section_only", "wrong_marker", "empty_setting"])
def test_marker_is_required_in_preamble(tmp_path: Path, config: Config, where: str) -> None:
    marker = config.privacy.synthetic_marker
    text = case_text("Synthetic data only")
    if where == "section_only":
        text += marker + "\n"
    if where == "wrong_marker":
        config.privacy.synthetic_marker = "Custom marker"
        text = case_text(marker)
    if where == "empty_setting":
        config.privacy.synthetic_marker = " "
    path = tmp_path / "marker.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(IngestError, match="^missing_marker at line 1$"):
        ingest_case(path, config)
    _, record = rejection_trace(config)
    assert record["error"] == "missing_marker at line 1"


def test_first_hit_only_and_distinct_rejection_folders(tmp_path: Path, config: Config) -> None:
    path = tmp_path / "multiple.md"
    path.write_text(case_text(config.privacy.synthetic_marker) +
                    "fictional@example.invalid\nPatient name: Fictional Example\n", encoding="utf-8")
    for _ in range(2):
        with pytest.raises(IngestError, match="email"):
            ingest_case(path, config)
    traces = list(Path(config.paths.runs).glob("*/trace.jsonl"))
    assert len(traces) == 2
    for trace in traces:
        events = trace.read_text().splitlines()
        assert len(events) == 1
        assert json.loads(events[0])["error"] == "email at line 10"


def test_trace_write_failure_is_redacted_and_still_blocks(
    tmp_path: Path, config: Config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "failure.md"
    path.write_text(case_text(config.privacy.synthetic_marker) + "fictional@example.invalid", encoding="utf-8")

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("fictional@example.invalid")

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(ValueError, match="privacy trace write failed: email at line 10") as caught:
        ingest_case(path, config)
    assert "fictional@example.invalid" not in "".join(traceback.format_exception(caught.value))
