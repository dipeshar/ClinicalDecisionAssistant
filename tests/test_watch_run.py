"""Read-only trace watcher: appended data, retries, failures and bad input."""

import json
from pathlib import Path

from tools import watch_run


def event(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "event_type": "llm_call", "step": "specialist", "role": "SURG", "round": 1,
        "attempt": 1, "repair": False, "error": None, "parsed_ref": None,
    }
    value.update(changes)
    return value


def encoded(value: object, *, newline: bool = True) -> bytes:
    suffix = b"\n" if newline else b""
    return json.dumps(value).encode("utf-8") + suffix


def decision() -> dict[str, object]:
    return event(event_type="decision", step="human", role=None, round=None,
                 parsed_ref="approved")


def test_watches_lines_appended_after_start(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_bytes(encoded(event()))
    output: list[str] = []
    sleeps = 0

    def append_decision(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        with trace.open("ab") as stream:
            stream.write(encoded(decision()))

    watch_run.watch_run(tmp_path, output=output.append, sleep_fn=append_decision)

    assert sleeps == 1
    assert output == ["Round 1 SURG: model responded", "Human decision recorded: approved"]


def test_holds_a_partial_final_line_until_it_is_complete(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    payload = encoded(event())
    split = len(payload) // 2
    trace.write_bytes(payload[:split])
    output: list[str] = []
    warnings: list[str] = []

    def finish_lines(_seconds: float) -> None:
        with trace.open("ab") as stream:
            stream.write(payload[split:] + encoded(decision()))

    watch_run.watch_run(
        tmp_path, output=output.append, warning_output=warnings.append, sleep_fn=finish_lines,
    )

    assert output == ["Round 1 SURG: model responded", "Human decision recorded: approved"]
    assert warnings == []


def test_reports_retry_repair_and_failure_without_claiming_validation(tmp_path: Path) -> None:
    values = [
        event(attempt=2),
        event(repair=True),
        event(role="PHYS", error="rate limited; retry later"),
        decision(),
    ]
    (tmp_path / "trace.jsonl").write_bytes(b"".join(encoded(value) for value in values))
    output: list[str] = []

    watch_run.watch_run(tmp_path, output=output.append, sleep_fn=lambda _seconds: None)

    assert output == [
        "Round 1 SURG: retry attempt 2; model responded",
        "Round 1 SURG: repair attempted; model responded",
        "Round 1 PHYS: call failed (rate limited; retry later)",
        "Human decision recorded: approved",
    ]
    assert not any(word in line.casefold() for line in output for word in ("finished", "succeeded", " ok"))


def test_every_role_and_round_gets_an_honest_subject() -> None:
    expected = {
        (1, "SURG"): "Round 1 SURG: model responded",
        (1, "PHYS"): "Round 1 PHYS: model responded",
        (1, "ANAES"): "Round 1 ANAES: model responded",
        (1, "ADMIN"): "Round 1 ADMIN: model responded",
        (1, "JUDGE_A"): "Round 1 JUDGE_A: model responded",
        (1, "JUDGE_B"): "Round 1 JUDGE_B: model responded",
        (2, "SURG"): "Round 2 SURG: model responded",
        (2, "PHYS"): "Round 2 PHYS: model responded",
        (2, "ANAES"): "Round 2 ANAES: model responded",
        (2, "ADMIN"): "Round 2 ADMIN: model responded",
        (2, "JUDGE_A"): "Round 2 JUDGE_A: model responded",
        (2, "JUDGE_B"): "Round 2 JUDGE_B: model responded",
    }
    for (round_number, role), line in expected.items():
        assert watch_run.format_event(event(round=round_number, role=role)) == line
    assert watch_run.format_event(event(step="red_team", role="RED", round=None)) == (
        "Red team: model responded"
    )
    assert watch_run.format_event(event(step="chair", role="CHAIR", round=None)) == (
        "Chair: model responded"
    )


def test_unknown_event_type_gets_an_honest_generic_line(tmp_path: Path) -> None:
    values = [event(event_type="future_event", step="future"), decision()]
    (tmp_path / "trace.jsonl").write_bytes(b"".join(encoded(value) for value in values))
    output: list[str] = []

    watch_run.watch_run(tmp_path, output=output.append, sleep_fn=lambda _seconds: None)

    assert output[0] == "Round 1 SURG: unknown event type 'future_event' recorded"


def test_waits_when_trace_does_not_exist_yet(tmp_path: Path) -> None:
    output: list[str] = []
    sleeps = 0

    def create_trace(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        (tmp_path / "trace.jsonl").write_bytes(encoded(decision()))

    watch_run.watch_run(tmp_path, output=output.append, sleep_fn=create_trace)

    assert sleeps == 1
    assert output == ["Human decision recorded: approved"]


def test_skips_malformed_complete_line_without_printing_its_content(tmp_path: Path) -> None:
    secret_bad_line = b'{"event_type": "llm_call", "prompt": "do not print me"\n'
    (tmp_path / "trace.jsonl").write_bytes(secret_bad_line + encoded(decision()))
    output: list[str] = []
    warnings: list[str] = []

    watch_run.watch_run(
        tmp_path, output=output.append, warning_output=warnings.append,
        sleep_fn=lambda _seconds: None,
    )

    assert output == ["Human decision recorded: approved"]
    assert warnings == ["Trace watcher: unreadable complete line skipped"]
    assert "do not print me" not in "".join(output + warnings)


def test_stop_request_safely_discards_an_incomplete_read(tmp_path: Path) -> None:
    (tmp_path / "trace.jsonl").write_bytes(b'{"event_type": "llm_call"')
    output: list[str] = []
    warnings: list[str] = []
    polls = 0

    def stop_requested() -> bool:
        nonlocal polls
        polls += 1
        return polls > 1

    watch_run.watch_run(
        tmp_path, output=output.append, warning_output=warnings.append,
        sleep_fn=lambda _seconds: None, stop_requested=stop_requested,
    )

    assert output == []
    assert warnings == []


def test_rejects_a_missing_run_folder(tmp_path: Path) -> None:
    missing = tmp_path / "not-a-run"

    try:
        watch_run.watch_run(missing)
    except ValueError as error:
        assert str(error) == f"run folder does not exist: {missing}"
    else:
        raise AssertionError("missing run folder was accepted")
