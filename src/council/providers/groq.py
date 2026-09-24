"""Groq adapter. Uses the `groq` SDK; no other module may import it (T8 checks this)."""

from collections.abc import Mapping
import re
from time import perf_counter

import groq

from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout

GROQ_KEY = re.compile(r"\bgsk_[A-Za-z0-9_-]+\b")


def safe_error_text(value: object) -> str:
    """Keep provider diagnostics while redacting Groq-shaped credentials."""
    return GROQ_KEY.sub("[REDACTED GROQ API KEY]", str(value)).strip()


def api_error_message(error: groq.APIStatusError) -> str:
    """Extract only the API's response-body message, never request data."""
    body: object = error.body
    if body is None:
        try:
            body = error.response.json()
        except ValueError:
            body = error.response.text
    if isinstance(body, Mapping):
        detail = body.get("error", body)
        if isinstance(detail, Mapping):
            message = detail.get("message", "")
        else:
            message = detail
    else:
        message = body
    return safe_error_text(message) if message else ""


def api_error_detail(error: groq.APIStatusError, label: str, *, retry_after: bool = False) -> str:
    """Format safe status/body diagnostics and an optional Retry-After value."""
    text = f"groq: {label} (status {error.status_code})"
    message = api_error_message(error)
    if message:
        text += f": {message}"
    if retry_after and (value := error.response.headers.get("Retry-After")) is not None:
        text += f"; Retry-After: {safe_error_text(value)}"
    return text


class GroqProvider(Provider):
    """One adapter, config-selected by model name. The API key is never touched here:

    the SDK reads `GROQ_API_KEY` from the environment on its own. Safe status and
    response-body diagnostics are retained, while Groq-shaped credentials are
    redacted before an exception can reach the trace.
    """

    name = "groq"

    def __init__(self, *, client: "groq.Groq | None" = None) -> None:
        self._client = client if client is not None else groq.Groq()

    def complete(self, *, model: str, system: str, user: str, max_tokens: int, temperature: float,
                reasoning_effort: str | None = None) -> ProviderResponse:
        start = perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=max_tokens, temperature=temperature,
                reasoning_effort=reasoning_effort, include_reasoning=True,
            )
        except groq.APITimeoutError as error:
            raise ProviderTimeout("groq: request timed out") from error
        except groq.RateLimitError as error:
            raise ProviderRateLimit(api_error_detail(error, "rate limited", retry_after=True)) from error
        except groq.APIStatusError as error:
            raise ProviderError(api_error_detail(error, type(error).__name__)) from error
        except groq.GroqError as error:
            raise ProviderError(f"groq: {type(error).__name__}") from error
        latency_ms = round((perf_counter() - start) * 1000)
        if response.usage is None:
            raise ProviderError("groq: response had no usage data")
        choice = response.choices[0]
        content = choice.message.content or ""
        return ProviderResponse(content, response.usage.prompt_tokens, response.usage.completion_tokens, latency_ms,
                                finish_reason=choice.finish_reason, reasoning=choice.message.reasoning)
