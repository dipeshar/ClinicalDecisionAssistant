"""FakeProvider: scripted outcomes drive specific scenarios without a real model."""

import pytest

from council.providers.base import ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout
from council.providers.fake import FakeProvider, Scripted


def test_good_output_is_returned_verbatim() -> None:
    provider = FakeProvider("fake", [Scripted(raw_output='{"stance": "for"}', tokens_in=5, tokens_out=6, latency_ms=9)])
    response = provider.complete(model="specialist", system="s", user="p", max_tokens=10, temperature=0.4)
    assert response == ProviderResponse('{"stance": "for"}', 5, 6, 9)


def test_bad_json_is_returned_as_plain_text_not_raised() -> None:
    provider = FakeProvider("fake", [Scripted(raw_output="{not valid json")])
    response = provider.complete(model="specialist", system="s", user="p", max_tokens=10, temperature=0.4)
    assert response.raw_output == "{not valid json"


def test_scripted_timeout_is_raised() -> None:
    provider = FakeProvider("fake", [ProviderTimeout])
    with pytest.raises(ProviderTimeout):
        provider.complete(model="specialist", system="s", user="p", max_tokens=10, temperature=0.4)


def test_scripted_rate_limit_is_raised() -> None:
    provider = FakeProvider("fake", [ProviderRateLimit])
    with pytest.raises(ProviderRateLimit):
        provider.complete(model="specialist", system="s", user="p", max_tokens=10, temperature=0.4)


def test_script_replays_in_order_one_outcome_per_call() -> None:
    provider = FakeProvider("fake", [ProviderTimeout, Scripted(raw_output="ok"), Scripted(raw_output="ok-2")])
    with pytest.raises(ProviderTimeout):
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    assert provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0).raw_output == "ok"
    assert provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0).raw_output == "ok-2"
    assert provider.calls_made == 3


def test_script_exhaustion_raises_provider_error() -> None:
    provider = FakeProvider("fake", [Scripted()])
    provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)
    with pytest.raises(ProviderError, match="exhausted"):
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)


def test_output_exceeding_the_reserved_cap_is_a_provider_error() -> None:
    provider = FakeProvider("fake", [Scripted(tokens_out=11)])
    with pytest.raises(ProviderError, match="exceeds"):
        provider.complete(model="m", system="s", user="p", max_tokens=10, temperature=0)


def test_empty_script_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one"):
        FakeProvider("fake", [])
