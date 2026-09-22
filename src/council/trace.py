"""Serialized JSONL audit events for decision support requiring clinical sign-off."""

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from council.models import TraceEvent


class TraceWriteError(RuntimeError):
    """Stop the run rather than silently lose its audit trail."""


class TraceWriter:
    """One writer per run. Refuse existing files; never overwrite a prior trace.

    The caller supplies a validated TraceEvent. run_id, seq and timestamp are
    overwritten by this writer. T8 owns secret removal before submission.
    """

    def __init__(self, path: str | Path, run_id: str) -> None:
        self._path = Path(path)
        self._run_id = run_id
        self._lock = Lock()
        self._seq = 0
        self._failed = False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("xb"):
                pass
        except OSError:
            raise TraceWriteError("cannot create a new trace file") from None

    def write(self, event: TraceEvent) -> TraceEvent:
        with self._lock:
            if self._failed:
                raise TraceWriteError("trace writer stopped after a write failure")
            data = event.model_dump()
            data.update(run_id=self._run_id, seq=self._seq + 1,
                        timestamp=datetime.now(timezone.utc).isoformat())
            recorded = TraceEvent.model_validate(data)
            payload = (recorded.model_dump_json() + "\n").encode("utf-8")
            try:
                with self._path.open("ab") as stream:
                    written = stream.write(payload)
                    if written != len(payload):
                        raise OSError("short trace write")
            except OSError:
                self._failed = True
                raise TraceWriteError("trace write failed; stop the run") from None
            self._seq = recorded.seq
            return recorded
