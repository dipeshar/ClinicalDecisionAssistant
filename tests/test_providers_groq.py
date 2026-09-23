"""GroqProvider against a stub client. No network access and no real API key."""

from types import SimpleNamespace

import groq
import httpx
import pytest

from council.providers.base import ProviderError, ProviderRateLimit, ProviderTimeout
from council.providers.groq import GroqProvider


class StubCompletions:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, messages: list[dict[str, str]], max_tokens: int,
              temperature: float) -> object:
        self.calls.append({"model": model, "messages": messages, "max_tokens": max_tokens,
                           "temperature": temperature})
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def stub_client(outcome: object) -> tuple[object, StubCompletions]:
    completions = StubCompletions(outcome)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def chat_completion(content: str | None = "hello", prompt_tokens: int = 10, completion_tokens: int = 5) -> object:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def http_error(cls: type[groq.APIStatusError], text: str) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request, text=text)
    return cls(text, response=response, body=None)


def test_good_response_returns_content_and_reported_usage() -> None:
    client, _ = stub_client(chat_completion(content="{}", prompt_tokens=12, completion_tokens=7))
    provider = GroqProvider(client=client)
    response = provider.complete(model="llama-3.3-70b-versatile", prompt="p", max_tokens=100, temperature=0.4)
    assert response.raw_output == "{}"
    assert response.tokens_in == 12
    assert response.tokens_out == 7
    assert response.latency_ms >= 0


def test_model_max_tokens_temperature_and_prompt_are_forwarded() -> None:
    client, completions = stub_client(chat_completion())
    provider = GroqProvider(client=client)
    provider.complete(model="qwen/qwen3-32b", prompt="synthetic prompt", max_tokens=42, temperature=0.1)
    assert completions.calls == [{
        "model": "qwen/qwen3-32b", "messages": [{"role": "user", "content": "synthetic prompt"}],
        "max_tokens": 42, "temperature": 0.1,
    }]


def test_missing_usage_is_a_provider_error() -> None:
    response = chat_completion()
    response.usage = None
    client, _ = stub_client(response)
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderError, match="no usage data"):
        provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)


def test_missing_message_content_becomes_empty_string() -> None:
    client, _ = stub_client(chat_completion(content=None))
    provider = GroqProvider(client=client)
    response = provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)
    assert response.raw_output == ""


def test_timeout_is_mapped_to_provider_timeout() -> None:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    client, _ = stub_client(groq.APITimeoutError(request))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderTimeout):
        provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)


def test_rate_limit_is_mapped_to_provider_rate_limit() -> None:
    client, _ = stub_client(http_error(groq.RateLimitError, "rate limited"))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderRateLimit):
        provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)


def test_other_groq_error_is_a_generic_provider_error() -> None:
    client, _ = stub_client(http_error(groq.AuthenticationError, "invalid api key"))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderError) as excinfo:
        provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)
    assert not isinstance(excinfo.value, (ProviderTimeout, ProviderRateLimit))


@pytest.mark.parametrize(("error_factory", "expected"), [
    (lambda key: groq.APITimeoutError(
        httpx.Request("POST", "https://api.groq.com/x", headers={"Authorization": f"Bearer {key}"})),
     ProviderTimeout),
    (lambda key: http_error(groq.RateLimitError, f"rate limited for key {key}"), ProviderRateLimit),
    (lambda key: http_error(groq.AuthenticationError, f"invalid key {key}"), ProviderError),
])
def test_api_key_never_leaks_into_a_raised_error_message(error_factory: object, expected: type) -> None:
    """Rule 21, re-run against the real adapter (T17): rerun of T8's leak test."""
    fake_key = "gsk_synthetic_fake_key_9f3c7a21e8"
    client, _ = stub_client(error_factory(fake_key))
    provider = GroqProvider(client=client)
    with pytest.raises(expected) as excinfo:
        provider.complete(model="m", prompt="p", max_tokens=10, temperature=0)
    assert fake_key not in str(excinfo.value)
