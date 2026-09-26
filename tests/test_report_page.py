"""T19: report.html is built from run.json, and case/model text is never HTML."""

from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path

import pytest

from council.cli import main, report_command
from council.models import RunBundle
from council.report_page import render_report_html, write_report_page
from tests.test_models import contract_samples

SCRIPT_PAYLOAD = "<script>window.__pwned = true;</script>"


def synthetic_bundle(*, script_in_case: bool = False, script_in_claim: bool = False) -> RunBundle:
    """A small, fully synthetic run bundle built from the models contract samples
    (tests/test_models.py), optionally with a literal <script> tag planted in
    case text or claim text - the two places model/case text reaches the page."""
    data = deepcopy(contract_samples()["RunBundle"])
    if script_in_case:
        data["case_context"]["sections"][0]["text"] += " " + SCRIPT_PAYLOAD
    if script_in_claim:
        data["arguments"][0]["claims"][0]["text"] += " " + SCRIPT_PAYLOAD
    return RunBundle.model_validate(data)


class _ScriptTagCounter(HTMLParser):
    """Counts real <script> elements as an HTML parser sees them - the only
    ground truth for whether a payload became a new script element."""

    def __init__(self) -> None:
        super().__init__()
        self.script_starts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.script_starts += 1


def test_page_has_exactly_the_two_script_elements_it_writes_itself() -> None:
    """However the fixture's text is mutated, an HTML parser must see exactly
    the two <script> elements report_page.py writes on purpose (the JSON data
    block and the app script) - never a third one born from embedded text."""
    bundle = synthetic_bundle(script_in_case=True, script_in_claim=True)
    html_text = render_report_html(bundle)
    counter = _ScriptTagCounter()
    counter.feed(html_text)
    assert counter.script_starts == 2


def test_script_payload_cannot_close_its_containing_script_early() -> None:
    """The literal `</script>` closing sequence must not appear anywhere in the
    output except to close the two script elements the module itself writes -
    otherwise a `</script>` inside embedded data could prematurely end the
    data block and let the rest of the payload be parsed as markup."""
    bundle = synthetic_bundle(script_in_case=True, script_in_claim=True)
    html_text = render_report_html(bundle)
    assert html_text.count("</script>") == 2


def test_script_text_survives_as_plain_data_for_the_page_to_display() -> None:
    """The payload isn't silently dropped - it is preserved byte-for-byte
    inside the JSON data block, so the page's own JS can show it as text."""
    bundle = synthetic_bundle(script_in_case=True, script_in_claim=True)
    html_text = render_report_html(bundle)
    start = html_text.index('<script id="council-run-data" type="application/json">') + len(
        '<script id="council-run-data" type="application/json">'
    )
    end = html_text.index("</script>", start)
    embedded = json.loads(html_text[start:end])
    assert SCRIPT_PAYLOAD in embedded["case_context"]["sections"][0]["text"]
    assert SCRIPT_PAYLOAD in embedded["arguments"][0]["claims"][0]["text"]


def test_plain_run_without_script_still_renders_two_script_elements() -> None:
    bundle = synthetic_bundle()
    html_text = render_report_html(bundle)
    counter = _ScriptTagCounter()
    counter.feed(html_text)
    assert counter.script_starts == 2


def test_report_page_shows_disclaimer_and_ids() -> None:
    bundle = synthetic_bundle()
    html_text = render_report_html(bundle)
    assert bundle.report.disclaimer in html_text
    assert bundle.run_id in html_text
    # The claim, argument and case-section IDs must reach the embedded data
    # so the page's own JS can register them as clickable.
    assert '"claim_id": "R1-SURG-C1"' in html_text or '"claim_id":"R1-SURG-C1"' in html_text
    assert "R1-SURG" in html_text
    assert "CASE-tests" in html_text


def test_write_report_page_reads_run_json_and_writes_report_html(tmp_path: Path) -> None:
    bundle = synthetic_bundle(script_in_case=True)
    run_folder = tmp_path / "run-20260925-000000-synthetic01"
    run_folder.mkdir()
    (run_folder / "run.json").write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_path = write_report_page(run_folder)
    assert output_path == run_folder / "report.html"
    written = output_path.read_text(encoding="utf-8")
    counter = _ScriptTagCounter()
    counter.feed(written)
    assert counter.script_starts == 2
    assert bundle.run_id in written


def test_write_report_page_requires_an_existing_run_json(tmp_path: Path) -> None:
    run_folder = tmp_path / "run-missing"
    run_folder.mkdir()
    with pytest.raises(FileNotFoundError):
        write_report_page(run_folder)


def test_cli_report_command_writes_the_page(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = synthetic_bundle()
    run_folder = tmp_path / "run-20260925-000001-synthetic01"
    run_folder.mkdir()
    (run_folder / "run.json").write_text(
        json.dumps(bundle.model_dump(mode="json")), encoding="utf-8",
    )
    output_path = report_command(run_folder)
    assert output_path.exists()
    assert "Wrote" in capsys.readouterr().out


def test_cli_main_report_subcommand(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = synthetic_bundle()
    run_folder = tmp_path / "run-20260925-000002-synthetic01"
    run_folder.mkdir()
    (run_folder / "run.json").write_text(
        json.dumps(bundle.model_dump(mode="json")), encoding="utf-8",
    )
    exit_code = main(["report", str(run_folder)])
    assert exit_code == 0
    assert (run_folder / "report.html").exists()


def test_cli_main_report_subcommand_reports_missing_run_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    run_folder = tmp_path / "run-missing"
    run_folder.mkdir()
    exit_code = main(["report", str(run_folder)])
    assert exit_code == 1
    assert "error:" in capsys.readouterr().err
