"""Provider interface for synthetic decision support requiring clinical sign-off.

Only this package may import a provider SDK (a test enforces that with a
static import check). Each real adapter is a small (about 30 line) class
that implements `complete` using that provider's own SDK. The gateway is the
only caller; agents never import a provider directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(RuntimeError):
    """The call failed. The gateway may retry within its fixed attempt budget."""


class ProviderTimeout(ProviderError):
    """The provider did not respond in time. The gateway retries this."""


class ProviderRateLimit(ProviderError):
    """The provider rejected the call for rate limiting. The gateway retries this."""


@dataclass(frozen=True)
class ProviderResponse:
    raw_output: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    finish_reason: str | None = None
    reasoning: str | None = None


class Provider(ABC):
    """One adapter per provider. Bad JSON is not this layer's job; return it as-is."""

    name: str

    @abstractmethod
    def complete(self, *, model: str, system: str, user: str, max_tokens: int, temperature: float,
                reasoning_effort: str | None = None) -> ProviderResponse:
        """Return one completion, or raise ProviderError / ProviderTimeout.

        `system` and `user` are sent as two separate messages, never concatenated
        into one: our own trusted instructions (persona, role instructions, rubric,
        repair text) in `system`, untrusted data (case text, retrieved passages,
        other arguments, judge notes) plus the response schema in `user`.
        """
