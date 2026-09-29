"""OpenRouterProvider against HTTPX mock transports; no network or real key."""

import httpx
import pytest

from council.providers.base import ProviderError, ProviderRateLimit, ProviderTimeout
from council.providers.openrouter import OPENROUTER_CHAT_URL, OpenRouterProvider

FAKE_KEY = "sk-or-v1-synthetic_fake_key_9f3c7a21e8"


def client_with(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def success_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, request=request, json={
        "choices": [{
            "message": {"content": "{}", "reasoning": "Synthetic reasoning"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    })


def test_good_response_and_openai_compatible_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success_response(request)

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    response = provider.complete(
        model="openai/gpt-oss-120b", system="trusted", user="untrusted",
        max_tokens=6000, temperature=0.4, reasoning_effort="low",
    )

    assert response.raw_output == "{}" and response.tokens_in == 12 and response.tokens_out == 7
    assert response.finish_reason == "stop" and response.reasoning == "Synthetic reasoning"
    [request] = requests
    assert str(request.url) == OPENROUTER_CHAT_URL
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert __import__("json").loads(request.content) == {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "trusted"},
            {"role": "user", "content": "untrusted"},
        ],
        "max_tokens": 6000,
        "temperature": 0.4,
        "reasoning": {"effort": "low"},
    }


@pytest.mark.parametrize("model", [
    "qwen/qwen3-235b-a22b-2507",
    "meta-llama/llama-3.3-70b-instruct",
])
def test_judge_request_omits_unsupported_reasoning_parameter(model: str) -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(__import__("json").loads(request.content))
        return success_response(request)

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    provider.complete(model=model, system="s", user="u", max_tokens=900, temperature=0,
                      reasoning_effort=None)
    assert "reasoning" not in payloads[0]
    assert "reasoning_effort" not in payloads[0]
    assert "include_reasoning" not in payloads[0]


def test_timeout_is_mapped_without_leaking_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out with {FAKE_KEY}", request=request)

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    with pytest.raises(ProviderTimeout) as excinfo:
        provider.complete(model="m", system="s", user="u", max_tokens=10, temperature=0)
    assert str(excinfo.value) == "openrouter: request timed out"
    assert FAKE_KEY not in str(excinfo.value)


def test_rate_limit_keeps_status_message_and_retry_after_but_redacts_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, request=request, headers={"Retry-After": "17"},
            json={"error": {"message": f"Limit reached for {FAKE_KEY}"}},
        )

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    with pytest.raises(ProviderRateLimit) as excinfo:
        provider.complete(model="m", system="s", user="u", max_tokens=10, temperature=0)
    text = str(excinfo.value)
    assert text == (
        "openrouter: rate limited (status 429): Limit reached for "
        "[REDACTED OPENROUTER API KEY]; Retry-After: 17"
    )
    assert FAKE_KEY not in text


def test_other_status_keeps_status_and_provider_message_but_redacts_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, request=request,
            json={"error": {"message": f"Credential {FAKE_KEY} is invalid"}},
        )

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    with pytest.raises(ProviderError) as excinfo:
        provider.complete(model="m", system="s", user="u", max_tokens=10, temperature=0)
    text = str(excinfo.value)
    assert text == (
        "openrouter: API error (status 401): Credential "
        "[REDACTED OPENROUTER API KEY] is invalid"
    )
    assert FAKE_KEY not in text


@pytest.mark.parametrize("body", [
    {},
    {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    {"choices": [{"message": {"content": "{}"}}]},
])
def test_invalid_response_shape_is_explicit(body: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=body)

    provider = OpenRouterProvider(api_key=FAKE_KEY, client=client_with(handler))
    with pytest.raises(ProviderError, match="invalid response shape"):
        provider.complete(model="m", system="s", user="u", max_tokens=10, temperature=0)
