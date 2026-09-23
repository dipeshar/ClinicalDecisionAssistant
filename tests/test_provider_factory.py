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
    # A synthetic key IS set, so a mutant that falls back to GROQ_API_KEY for any
    # unknown name would wrongly succeed instead of raising; this isolates that case
    # from the separate missing-key path.
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_test_key_not_real")
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


def test_build_providers_inspects_every_role_not_only_specialist(
    config: Config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A judge-only provider must surface, proving every role field is read, not just specialist."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_synthetic_test_key_not_real")
    mixed_models = config.models.model_copy(update={
        "specialist": config.models.specialist.model_copy(update={"provider": "groq"}),
        "chair": config.models.chair.model_copy(update={"provider": "groq"}),
        "red_team": config.models.red_team.model_copy(update={"provider": "groq"}),
        "judge_a": config.models.judge_a.model_copy(update={"provider": "openai"}),
        "judge_b": config.models.judge_b.model_copy(update={"provider": "groq"}),
    })
    mixed_config = config.model_copy(update={"models": mixed_models})

    with pytest.raises(ProviderConfigurationError, match="'openai'"):
        build_providers(mixed_config)
