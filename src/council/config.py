"""Configuration for synthetic decision support requiring clinical sign-off."""

from pathlib import Path
from typing import Final

from pydantic import ValidationError
import yaml

from council.models import Config, Role

MAX_ROUNDS: Final = 2
SPECIALISTS: Final = {Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN}
CASE_SECTIONS: Final = {
    "CASE-profile", "CASE-diagnoses", "CASE-comorbidities", "CASE-medications",
    "CASE-allergies", "CASE-tests", "CASE-procedure", "CASE-consultant-review",
}


class ConfigError(ValueError):
    """A configuration file could not be read or violates the contracts."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loading that also rejects silently overwritten settings."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[object, object]:
        keys: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
                keys.add(key)
            except TypeError as error:
                raise ConfigError("YAML setting names must be scalar values") from error
            if duplicate:
                raise ConfigError(f"duplicate YAML setting at line {key_node.start_mark.line + 1}")
        return super().construct_mapping(node, deep=deep)


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read YAML, validate its shape and policy, and return the existing Config model."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ConfigError(f"cannot read configuration file: {path}") from error
    try:
        data = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ConfigError("invalid YAML in configuration file") from error
    if not isinstance(data, dict):
        raise ConfigError("configuration must be a YAML mapping")
    if "max_rounds" in data:
        raise ConfigError("max_rounds is a code constant (2), not a setting")
    # Strict validation accepts enum instances; YAML naturally supplies string keys.
    if isinstance(data.get("roles"), dict):
        try:
            data["roles"] = {Role(key): value for key, value in data["roles"].items()}
        except ValueError as error:
            raise ConfigError("roles contains an unknown role code") from error
    try:
        config = Config.model_validate(data, strict=True)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        )
        raise ConfigError(f"invalid configuration: {details}") from error
    validate_config(config)
    return config


def require(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise ConfigError(f"{field}: {message}")


def validate_config(config: Config) -> None:
    """Validate the contract rules without loading prompts, KBs or provider SDKs."""
    validate_budget(config)
    validate_limits(config)
    validate_roles(config)
    validate_privacy(config)
    validate_models(config)


def validate_privacy(config: Config) -> None:
    require(bool(config.privacy.synthetic_marker.strip()), "privacy.synthetic_marker", "must not be blank")
    require(all(name.strip() and name == name.strip() for name in config.privacy.approved_providers),
            "privacy.approved_providers", "must contain nonblank provider names without surrounding spaces")


def validate_budget(config: Config) -> None:
    budget = config.budget
    for field in ("max_total_tokens", "max_calls", "max_seconds_total"):
        require(getattr(budget, field) > 0, f"budget.{field}", "must be positive")
    for role, cap in budget.max_tokens_per_call.model_dump().items():
        require(cap > 0, f"budget.max_tokens_per_call.{role}", "must be positive")
    for field, total in (("tokens", budget.max_total_tokens), ("seconds", budget.max_seconds_total),
                         ("calls", budget.max_calls)):
        reserve = getattr(budget.chair_reserve, field)
        require(0 < reserve < total, f"budget.chair_reserve.{field}",
                "must be positive and smaller than the total budget")
    require(budget.chair_reserve.tokens >= budget.max_tokens_per_call.chair,
            "budget.chair_reserve.tokens", "must cover the chair output cap")


def validate_limits(config: Config) -> None:
    fixed = {
        "retries.max_repair_retries_per_turn": (config.retries.max_repair_retries_per_turn, 1),
        "retries.max_api_attempts": (config.retries.max_api_attempts, 2),
        "retrieval.top_k": (config.retrieval.top_k, 5),
        "grounding.quote_words_min": (config.grounding.quote_words_min, 4),
        "grounding.quote_words_max": (config.grounding.quote_words_max, 40),
        "judging.disagreement_gap": (config.judging.disagreement_gap, 2),
        "judging.feedback_max_notes": (config.judging.feedback_max_notes, 5),
        "judging.feedback_max_words": (config.judging.feedback_max_words, 40),
    }
    for field, (value, expected) in fixed.items():
        require(value == expected, field, f"must be {expected} under the current contracts")
    require(config.retries.api_retry_wait_seconds >= 0, "retries.api_retry_wait_seconds", "must not be negative")
    for role, temperature in config.temperature.model_dump().items():
        require(temperature >= 0, f"temperature.{role}", "must not be negative")
    require(bool(config.retrieval.case_sections) and set(config.retrieval.case_sections) <= CASE_SECTIONS,
            "retrieval.case_sections", "must contain known case section IDs")


def validate_roles(config: Config) -> None:
    require(set(config.roles) == SPECIALISTS | {Role.RED}, "roles", "must contain SURG, PHYS, ANAES, ADMIN and RED")
    for field, path in config.paths.model_dump().items():
        require(bool(path.strip()), f"paths.{field}", "must not be blank")
    for role, settings in config.roles.items():
        for field in ("name", "kb"):
            require(bool(getattr(settings, field).strip()), f"roles.{role}.{field}", "must not be blank")
        require(bool(settings.keywords) and all(word.strip() for word in settings.keywords),
                f"roles.{role}.keywords", "must contain nonblank keywords")
        if role in SPECIALISTS:
            require(bool(settings.persona_prompt and settings.persona_prompt.strip()),
                    f"roles.{role}.persona_prompt", "specialists need a persona prompt filename")


def validate_models(config: Config) -> None:
    models = config.models
    for role, choice in models.model_dump().items():
        for field, value in choice.items():
            require(bool(value.strip()) and value.strip().upper() != "TBD",
                    f"models.{role}.{field}", "replace TBD/blank with a provider or model name")
    for field in ("provider", "model"):
        require(getattr(models.chair, field) == getattr(models.specialist, field),
                f"models.chair.{field}", "must match the specialist provider and model")
        require(getattr(models.judge_a, field) == getattr(models.judge_b, field),
                f"models.judge_b.{field}", "must match Judge A's provider and model")
    require(models.judge_a != models.specialist, "models.judge_a", "judges must use a different model from specialists")
    for role, choice in models.model_dump().items():
        require(choice["provider"] in config.privacy.approved_providers,
                f"models.{role}.provider", "must be in privacy.approved_providers")
