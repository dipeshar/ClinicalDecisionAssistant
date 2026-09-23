"""Builds real Provider instances from config. Only this module reads a provider API key."""

import os
from typing import Final

import groq

from council.models import Config
from council.providers.base import Provider
from council.providers.groq import GroqProvider

# One entry per provider name that can appear in config.yaml's `models` block.
PROVIDER_ENV_VARS: Final[dict[str, str]] = {"groq": "GROQ_API_KEY"}


class ProviderConfigurationError(RuntimeError):
    """A configured provider cannot be built (unknown name or missing API key)."""


def build_provider(name: str) -> Provider:
    """Construct the real adapter for one provider name, reading its key from the
    environment at call time. The key is read once into a local variable and passed
    straight into the SDK client constructor; it is never logged, printed, or put
    into an exception message anywhere in this function."""
    env_var = PROVIDER_ENV_VARS.get(name)
    if env_var is None:
        raise ProviderConfigurationError(f"no provider adapter is registered for {name!r}")
    api_key = os.environ.get(env_var)
    if not api_key:
        raise ProviderConfigurationError(
            f"{env_var} is not set; set it in your environment before running with provider {name!r}"
        )
    return GroqProvider(client=groq.Groq(api_key=api_key))


def build_providers(config: Config) -> dict[str, Provider]:
    """One real Provider per distinct provider name used across every configured role."""
    names = {choice.provider for choice in (
        config.models.specialist, config.models.chair, config.models.red_team,
        config.models.judge_a, config.models.judge_b,
    )}
    return {name: build_provider(name) for name in names}
