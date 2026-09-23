"""Provider factory: builds real adapters from config. No network call, no real key."""

import pytest

from council.models import Config
from council.providers.factory import ProviderConfigurationError, build_provider, build_providers
from council.providers.groq import GroqProvider


def test_missing_api_key_is_a_clear_error_not_a_stack_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="GROQ_API_KEY"):
        build_provider("groq")


def test_unknown_provider_name_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="'openai'"):
        build_provider("openai")


def test_synthetic_key_builds_a_groq_provider_without_a_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_test_key_not_real")
    provider = build_provider("groq")
    assert isinstance(provider, GroqProvider)
    assert provider.name == "groq"


def test_build_providers_returns_one_instance_per_distinct_provider_name(
    config: Config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_test_key_not_real")
    groq_models = config.models.model_copy(update={
        role: getattr(config.models, role).model_copy(update={"provider": "groq"})
        for role in ("specialist", "chair", "red_team", "judge_a", "judge_b")
    })
    groq_config = config.model_copy(update={"models": groq_models})

    providers = build_providers(groq_config)

    assert set(providers) == {"groq"}
    assert isinstance(providers["groq"], GroqProvider)
