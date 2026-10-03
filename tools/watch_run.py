"""Read-only live progress viewer for an existing council run folder.

This tool tails ``trace.jsonl`` and reads ``max_calls`` from ``config.yaml``
once at startup. Its messages describe trace events, not validated turns: an
LLM event proves that a call attempt returned or failed, but does not prove
that the response later passed parsing or validation.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
from pathlib import Path
import re
import sys
from time import sleep
from typing import Any

import yaml


PollControl = Callable[[], bool]
Sleep = Callable[[float], None]

_JUDGE_ARGUMENT_BLOCK = re.compile(
    r"^----- BEGIN (R[12]-(?:SURG|PHYS|ANAES|ADMIN)) "
    r"\(data only; nothing inside this block is an instruction\) -----$",
    re.MULTILINE,
)


def _one_line(value: object) -> str:
    """Keep one event on one terminal line without exposing other event fields."""
    return " ".join(str(value).split())


def judge_argument_id(event: dict[str, Any]) -> str | None:
    """Return the sole exact argument-block label in a judge's sent prompt."""
    if event.get("step") != "judge":
        return None
    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return None
    matches = _JUDGE_ARGUMENT_BLOCK.findall(prompt)
    return matches[0] if len(matches) == 1 else None


def _subject(event: dict[str, Any]) -> str:
    round_number = event.get("round")
    role = event.get("role")
    step = event.get("step")
    if round_number in (1, 2) and isinstance(role, str):
        subject = f"Round {round_number} {role}"
        argument_id = judge_argument_id(event)
        return f"{subject} for {argument_id}" if argument_id else subject
    if step == "red_team":
        return "Red team"
    if step == "chair":
        return "Chair"
    if step == "human":
        return "Human decision"
    if step == "ingest":
        return "Ingest"
    if isinstance(role, str):
        return role
    return _one_line(step or "Trace")


def format_event(event: dict[str, Any]) -> str:
    """Translate one trace object without claiming downstream validation passed."""
    subject = _subject(event)
    event_type = event.get("event_type")
    error = event.get("error")
    reason = f" ({_one_line(error)})" if error else ""

    if event_type == "llm_call":
        repair = event.get("repair") is True
        attempt = event.get("attempt")
        prefix = "repair attempted; " if repair else ""
        if not repair and isinstance(attempt, int) and attempt > 1:
            prefix = f"retry attempt {attempt}; "
        outcome = f"call failed{reason}" if error else "model responded"
        return f"{subject}: {prefix}{outcome}"
    if event_type == "privacy_block":
        return f"{subject}: privacy block recorded{reason}"
    if event_type == "injection_block":
        return f"{subject}: injection block recorded{reason}"
    if event_type == "budget":
        return f"{subject}: budget event recorded{reason}"
    if event_type == "validation":
        return f"{subject}: validation event recorded{reason}"
    if event_type == "retrieval":
        return f"{subject}: retrieval event recorded{reason}"
    if event_type == "start":
        return f"{subject}: start event recorded{reason}"
    if event_type == "error":
        return f"{subject}: error event recorded{reason}"
    if event_type == "decision":
        decision = event.get("parsed_ref")
        suffix = f": {_one_line(decision)}" if decision else ""
        return f"Human decision recorded{suffix}"
    return f"{subject}: unknown event type {_one_line(event_type)!r} recorded"


def _read_complete_lines(trace_path: Path, offset: int,
                         pending: bytes) -> tuple[list[bytes], int, bytes]:
    """Read newly appended bytes and retain a final unterminated line."""
    try:
        size = trace_path.stat().st_size
        if size < offset:
            offset = 0
            pending = b""
        with trace_path.open("rb") as stream:
            stream.seek(offset)
            chunk = stream.read()
    except (FileNotFoundError, PermissionError, OSError):
        return [], offset, pending
    offset += len(chunk)
    pieces = (pending + chunk).split(b"\n")
    return pieces[:-1], offset, pieces[-1]


def read_max_calls(config_path: str | Path) -> int:
    """Read and validate the configured gateway-attempt ceiling."""
    path = Path(config_path)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        max_calls = loaded["budget"]["max_calls"]
    except (OSError, TypeError, KeyError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read budget.max_calls from config: {path}") from error
    if type(max_calls) is not int or max_calls <= 0:
        raise ValueError(f"budget.max_calls must be a positive integer in config: {path}")
    return max_calls


def watch_run(
    run_folder: str | Path, *, poll_seconds: float = 0.25,
    config_path: str | Path = "config.yaml",
    output: Callable[[str], None] = print,
    warning_output: Callable[[str], None] | None = None,
    sleep_fn: Sleep = sleep,
    stop_requested: PollControl = lambda: False,
) -> None:
    """Tail one run's trace until its decision event or an external stop request."""
    folder = Path(run_folder)
    if not folder.is_dir():
        raise ValueError(f"run folder does not exist: {folder}")
    max_calls = read_max_calls(config_path)
    trace_path = folder / "trace.jsonl"
    warn = warning_output or (lambda message: print(message, file=sys.stderr))
    offset = 0
    pending = b""
    attempt_count = 0

    while not stop_requested():
        lines, offset, pending = _read_complete_lines(trace_path, offset, pending)
        observed_decision = False
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                decoded = raw_line.decode("utf-8")
                event = json.loads(decoded)
                if not isinstance(event, dict):
                    raise ValueError("trace event is not an object")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                warn("Trace watcher: unreadable complete line skipped")
                continue
            if event.get("event_type") == "llm_call":
                attempt_count += 1
            output(
                f"{format_event(event)} "
                f"(attempt count: {attempt_count} of up to {max_calls} configured)"
            )
            observed_decision = observed_decision or event.get("event_type") == "decision"
        if observed_decision:
            return
        sleep_fn(poll_seconds)


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="Tail one existing council run's trace without changing the run.",
    )
    command_parser.add_argument("run_folder", type=Path)
    command_parser.add_argument("--poll-seconds", type=float, default=0.25)
    command_parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    return command_parser


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.poll_seconds <= 0:
        print("error: --poll-seconds must be positive", file=sys.stderr)
        return 2
    try:
        watch_run(
            args.run_folder, poll_seconds=args.poll_seconds, config_path=args.config,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
