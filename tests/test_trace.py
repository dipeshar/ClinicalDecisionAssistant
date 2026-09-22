"""JSONL serialization and shared budget/trace concurrency with synthetic data."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier, Event
from time import sleep

import pytest

from council.budget import Budget
from council.models import BudgetConfig, Role, TraceEvent
from council.trace import TraceWriteError, TraceWriter


def event(**changes: object) -> TraceEvent:
    fields = dict(run_id="caller-run", seq=999, timestamp="caller-time", step="specialist",
                  event_type="llm_call", role="SURG", round=1, model="fake/synthetic",
                  prompt="Synthetic prompt\nsecond line", retrieved_passage_ids=["CASE-tests"],
                  raw_output='{"synthetic": true}\n', parsed_ref="R1-SURG", tokens_in=2,
                  tokens_out=3, latency_ms=1, attempt=1, repair=False, budget_tokens_used=5, error=None)
    fields.update(changes)
    return TraceEvent.model_validate(fields)


def test_trace_jsonl_preserves_fields_and_owns_order_and_time(tmp_path: Path) -> None:
    path = tmp_path / "run-synthetic" / "trace.jsonl"
    writer = TraceWriter(path, "run-synthetic")
    original = event()
    before = original.model_dump()
    first, second = writer.write(original), writer.write(event(attempt=2, repair=True))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    records = [TraceEvent.model_validate_json(line) for line in lines]
    assert records == [first, second]
    assert [r.seq for r in records] == [1, 2]
    assert all(r.run_id == "run-synthetic" for r in records)
    assert datetime.fromisoformat(first.timestamp).utcoffset().total_seconds() == 0
    assert original.model_dump() == before
    for field, value in before.items():
        if field not in {"run_id", "seq", "timestamp"}:
            assert getattr(first, field) == value


def test_existing_trace_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    first = TraceWriter(path, "synthetic")
    first.write(event())
    before = path.read_bytes()
    with pytest.raises(TraceWriteError, match="cannot create"):
        TraceWriter(path, "another")
    assert path.read_bytes() == before


def test_write_failure_is_explicit_and_writer_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = TraceWriter(tmp_path / "trace.jsonl", "synthetic")
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic private filename")
    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(TraceWriteError, match="trace write failed") as caught:
        writer.write(event())
    assert "private filename" not in str(caught.value)
    with pytest.raises(TraceWriteError, match="stopped after"):
        writer.write(event())


def test_short_write_stops_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = TraceWriter(tmp_path / "trace.jsonl", "synthetic")
    class ShortStream:
        def __enter__(self) -> "ShortStream":
            return self
        def __exit__(self, *args: object) -> None:
            pass
        def write(self, payload: bytes) -> int:
            return len(payload) - 1
    def short_open(*args: object, **kwargs: object) -> ShortStream:
        return ShortStream()
    monkeypatch.setattr(Path, "open", short_open)
    with pytest.raises(TraceWriteError, match="trace write failed"):
        writer.write(event())


def test_trace_write_waits_for_shared_lock(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer, entered = TraceWriter(path, "synthetic"), Event()
    def work() -> None:
        entered.set()
        writer.write(event())
    with ThreadPoolExecutor(max_workers=1) as pool:
        with writer._lock:
            future = pool.submit(work)
            assert entered.wait(timeout=5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
            assert path.read_bytes() == b""
        future.result(timeout=5)


def test_parallel_budget_and_trace_no_lost_tokens_or_sequence_gaps(
    tmp_path: Path, request: pytest.FixtureRequest,
) -> None:
    threads = 32
    iterations = request.config.getoption("--race-iterations")
    assert iterations > 0
    count = threads * iterations
    config = BudgetConfig(
        max_total_tokens=count * 20 + 1000, max_calls=count + 10, max_seconds_total=3600,
        chair_reserve=dict(tokens=100, calls=2, seconds=10),
        max_tokens_per_call=dict(specialist=10, judge=10, red_team=10, chair=10),
    )
    budget, barrier = Budget(config), Barrier(threads)
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path, "run-concurrency-synthetic")

    def work(worker: int) -> int:
        barrier.wait(timeout=10)
        expected = 0
        for iteration in range(iterations):
            incoming, outgoing = iteration % 7 + 1, iteration % 5 + 1
            ticket = budget.check_and_reserve(Role.SURG, incoming)
            sleep(0)  # Deliberately interleave admission, settlement and writing.
            state = budget.complete(ticket, incoming, outgoing)
            writer.write(event(parsed_ref=f"synthetic-{worker}-{iteration}",
                               tokens_in=incoming, tokens_out=outgoing,
                               budget_tokens_used=state.tokens_used))
            expected += incoming + outgoing
        return expected

    with ThreadPoolExecutor(max_workers=threads) as pool:
        expected_tokens = sum(pool.map(work, range(threads)))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == count
    assert [row["seq"] for row in rows] == list(range(1, count + 1))
    assert {row["parsed_ref"] for row in rows} == {
        f"synthetic-{worker}-{iteration}" for worker in range(threads) for iteration in range(iterations)
    }
    assert sum(row["tokens_in"] + row["tokens_out"] for row in rows) == expected_tokens
    state = budget.snapshot()
    assert state.tokens_used == expected_tokens
    assert state.calls_used == count and not state.exhausted
    assert max(row["budget_tokens_used"] for row in rows) == expected_tokens
    print(f"Race check: {threads} threads x {iterations} iterations = {count} calls/events; "
          f"{expected_tokens} tokens; seq 1..{count} unique and gapless")
