"""Deterministic provider for tests. Never calls a real model or the network."""

from dataclasses import dataclass
from threading import Lock
from typing import Sequence

from council.providers.base import Provider, ProviderError, ProviderResponse


@dataclass(frozen=True)
class Scripted:
    """One scripted successful outcome.

    Use any text for `raw_output`, including invalid JSON: bad-JSON handling
    belongs to the caller's repair logic (grounding.py, agents/*), not here.
    """

    raw_output: str = "{}"
    tokens_in: int = 1
    tokens_out: int = 1
    latency_ms: int = 1


class FakeProvider(Provider):
    """Replays a fixed script, one entry per call, in order.

    Each entry is either a `Scripted` success or an exception type (for
    example `ProviderTimeout`) to raise instead, so a test can script a
    turn's exact sequence: good output, bad JSON, a timeout, and so on.
    """

    def __init__(self, name: str, script: Sequence[Scripted | type[BaseException]]) -> None:
        if not script:
            raise ValueError("a fake provider needs at least one scripted outcome")
        self.name = name
        self._script = list(script)
        self._index = 0
        self._lock = Lock()

    def complete(self, *, model: str, prompt: str, max_tokens: int, temperature: float) -> ProviderResponse:
        with self._lock:
            if self._index >= len(self._script):
                raise ProviderError(f"{self.name}: fake provider script exhausted")
            outcome = self._script[self._index]
            self._index += 1
        if isinstance(outcome, type) and issubclass(outcome, BaseException):
            raise outcome(f"{self.name}: scripted failure")
        if outcome.tokens_out > max_tokens:
            raise ProviderError(f"{self.name}: scripted output exceeds the reserved cap")
        return ProviderResponse(outcome.raw_output, outcome.tokens_in, outcome.tokens_out, outcome.latency_ms)

    @property
    def calls_made(self) -> int:
        with self._lock:
            return self._index
