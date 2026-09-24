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

    def create(self, *, model: str, messages: list[dict[str, str]], max_tokens: int, temperature: float,
              reasoning_effort: str | None, include_reasoning: bool) -> object:
        self.calls.append({"model": model, "messages": messages, "max_tokens": max_tokens,
                           "temperature": temperature, "reasoning_effort": reasoning_effort,
                           "include_reasoning": include_reasoning})
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def stub_client(outcome: object) -> tuple[object, StubCompletions]:
    completions = StubCompletions(outcome)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def chat_completion(content: str | None = "hello", prompt_tokens: int = 10, completion_tokens: int = 5,
                    finish_reason: str | None = "stop", reasoning: str | None = None) -> object:
    message = SimpleNamespace(content=content, reasoning=reasoning)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def http_error(cls: type[groq.APIStatusError], text: str, *, status: int = 429,
               headers: dict[str, str] | None = None) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    body = {"error": {"message": text}}
    response = httpx.Response(status, request=request, headers=headers, json=body)
    return cls(text, response=response, body=body)


def test_good_response_returns_content_and_reported_usage() -> None:
    client, _ = stub_client(chat_completion(content="{}", prompt_tokens=12, completion_tokens=7,
                                            finish_reason="stop", reasoning="Synthetic reasoning trace"))
    provider = GroqProvider(client=client)
    response = provider.complete(model="openai/gpt-oss-120b", system="s", user="u", max_tokens=100,
                                 temperature=0.4)
    assert response.raw_output == "{}"
    assert response.tokens_in == 12
    assert response.tokens_out == 7
    assert response.latency_ms >= 0
    assert response.finish_reason == "stop"
    assert response.reasoning == "Synthetic reasoning trace"


def test_model_max_tokens_temperature_and_reasoning_effort_are_forwarded() -> None:
    client, completions = stub_client(chat_completion())
    provider = GroqProvider(client=client)
    provider.complete(model="qwen/qwen3.8-27b", system="synthetic system", user="synthetic user",
                      max_tokens=42, temperature=0.1, reasoning_effort="low")
    assert completions.calls == [{
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "system", "content": "synthetic system"},
                     {"role": "user", "content": "synthetic user"}],
        "max_tokens": 42, "temperature": 0.1, "reasoning_effort": "low", "include_reasoning": True,
    }]


def test_system_and_user_are_sent_as_two_separate_messages_not_one() -> None:
    """The real security fix (design.md, "Prompt injection defense"): our own
    instructions and the untrusted data must never be concatenated into one
    flattened user message."""
    client, completions = stub_client(chat_completion())
    provider = GroqProvider(client=client)
    provider.complete(model="m", system="trusted instructions", user="untrusted case data",
                      max_tokens=10, temperature=0)
    [call] = completions.calls
    assert call["messages"] == [
        {"role": "system", "content": "trusted instructions"},
        {"role": "user", "content": "untrusted case data"},
    ]
    assert len(call["messages"]) == 2


def test_include_reasoning_is_always_requested_even_with_no_reasoning_effort() -> None:
    client, completions = stub_client(chat_completion())
    provider = GroqProvider(client=client)
    provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert completions.calls == [{
        "model": "m", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "p"}],
        "max_tokens": 10, "temperature": 0, "reasoning_effort": None, "include_reasoning": True,
    }]


def test_missing_usage_is_a_provider_error() -> None:
    response = chat_completion()
    response.usage = None
    client, _ = stub_client(response)
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderError, match="no usage data"):
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)


def test_missing_message_content_becomes_empty_string() -> None:
    client, _ = stub_client(chat_completion(content=None))
    provider = GroqProvider(client=client)
    response = provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert response.raw_output == ""


def test_timeout_is_mapped_to_provider_timeout() -> None:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    client, _ = stub_client(groq.APITimeoutError(request))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderTimeout):
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)


def test_rate_limit_is_mapped_to_provider_rate_limit() -> None:
    client, _ = stub_client(http_error(
        groq.RateLimitError, "Requests exceeded the project limit.", headers={"Retry-After": "17"},
    ))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderRateLimit) as excinfo:
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert str(excinfo.value) == (
        "groq: rate limited (status 429): Requests exceeded the project limit.; Retry-After: 17"
    )


def test_rate_limit_without_retry_after_does_not_invent_header() -> None:
    client, _ = stub_client(http_error(groq.RateLimitError, "Requests exceeded the project limit."))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderRateLimit) as excinfo:
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert "Retry-After" not in str(excinfo.value)


def test_other_groq_error_is_a_generic_provider_error() -> None:
    client, _ = stub_client(http_error(
        groq.AuthenticationError, "The supplied credential is invalid.", status=401,
    ))
    provider = GroqProvider(client=client)
    with pytest.raises(ProviderError) as excinfo:
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert not isinstance(excinfo.value, (ProviderTimeout, ProviderRateLimit))
    assert str(excinfo.value) == (
        "groq: AuthenticationError (status 401): The supplied credential is invalid."
    )


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
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert fake_key not in str(excinfo.value)
