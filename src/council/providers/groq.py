"""Groq adapter. Uses the `groq` SDK; no other module may import it (T8 checks this)."""

from time import perf_counter

import groq

from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout


class GroqProvider(Provider):
    """One adapter, config-selected by model name. The API key is never touched here:

    the SDK reads `GROQ_API_KEY` from the environment on its own; this class never
    reads, prints or logs it, and no exception message below repeats the SDK's own
    error text, so a key embedded in a response body can never reach the trace.
    """

    name = "groq"

    def __init__(self, *, client: "groq.Groq | None" = None) -> None:
        self._client = client if client is not None else groq.Groq()

    def complete(self, *, model: str, prompt: str, max_tokens: int, temperature: float,
                reasoning_effort: str | None = None) -> ProviderResponse:
        start = perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=temperature,
                reasoning_effort=reasoning_effort, include_reasoning=True,
            )
        except groq.APITimeoutError as error:
            raise ProviderTimeout("groq: request timed out") from error
        except groq.RateLimitError as error:
            raise ProviderRateLimit("groq: rate limited") from error
        except groq.GroqError as error:
            raise ProviderError(f"groq: {type(error).__name__}") from error
        latency_ms = round((perf_counter() - start) * 1000)
        if response.usage is None:
            raise ProviderError("groq: response had no usage data")
        choice = response.choices[0]
        content = choice.message.content or ""
        return ProviderResponse(content, response.usage.prompt_tokens, response.usage.completion_tokens, latency_ms,
                                finish_reason=choice.finish_reason, reasoning=choice.message.reasoning)
