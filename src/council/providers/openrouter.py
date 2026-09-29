"""OpenRouter adapter using its OpenAI-compatible chat-completions API."""

from collections.abc import Mapping
import re
from time import perf_counter
from typing import Any

import httpx

from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]+\b")


class OpenRouterProvider(Provider):
    """Small synchronous adapter; credentials never enter errors or trace data."""

    name = "openrouter"

    def __init__(self, *, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client if client is not None else httpx.Client(timeout=60.0)

    def _safe_text(self, value: object) -> str:
        text = str(value).replace(self._api_key, "[REDACTED OPENROUTER API KEY]")
        return OPENROUTER_KEY.sub("[REDACTED OPENROUTER API KEY]", text).strip()

    def _error_message(self, response: httpx.Response) -> str:
        try:
            body: object = response.json()
        except ValueError:
            body = response.text
        if isinstance(body, Mapping):
            detail = body.get("error", body)
            message = detail.get("message", "") if isinstance(detail, Mapping) else detail
        else:
            message = body
        return self._safe_text(message) if message else ""

    def _error_detail(self, response: httpx.Response, label: str, *, retry_after: bool = False) -> str:
        text = f"openrouter: {label} (status {response.status_code})"
        if message := self._error_message(response):
            text += f": {message}"
        if retry_after and (value := response.headers.get("Retry-After")) is not None:
            text += f"; Retry-After: {self._safe_text(value)}"
        return text

    def complete(self, *, model: str, system: str, user: str, max_tokens: int, temperature: float,
                 reasoning_effort: str | None = None) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}

        start = perf_counter()
        try:
            response = self._client.post(
                OPENROUTER_CHAT_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as error:
            raise ProviderTimeout("openrouter: request timed out") from error
        except httpx.HTTPError as error:
            raise ProviderError(f"openrouter: {type(error).__name__}") from error

        if response.status_code == 429:
            raise ProviderRateLimit(self._error_detail(response, "rate limited", retry_after=True))
        if response.is_error:
            raise ProviderError(self._error_detail(response, "API error"))

        try:
            body = response.json()
            usage = body["usage"]
            choice = body["choices"][0]
            message = choice["message"]
            tokens_in = usage["prompt_tokens"]
            tokens_out = usage["completion_tokens"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError("openrouter: invalid response shape") from error
        if type(tokens_in) is not int or type(tokens_out) is not int:
            raise ProviderError("openrouter: invalid usage data")

        content = message.get("content") or ""
        reasoning = message.get("reasoning")
        if reasoning is not None and not isinstance(reasoning, str):
            reasoning = str(reasoning)
        latency_ms = round((perf_counter() - start) * 1000)
        return ProviderResponse(
            str(content), tokens_in, tokens_out, latency_ms,
            finish_reason=choice.get("finish_reason"), reasoning=reasoning,
        )
