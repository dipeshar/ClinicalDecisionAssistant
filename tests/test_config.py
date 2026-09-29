"""Configuration tests use synthetic provider names and make no model calls."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from council.config import ConfigError, MAX_ROUNDS, load_config


@pytest.fixture
def valid_data() -> dict[str, Any]:
    data = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    for role in ("specialist", "chair", "red_team"):
        data["models"][role] = dict(provider="fake", model="synthetic-specialist")
    data["models"]["judge_a"] = dict(provider="fake", model="synthetic-judge-a")
    data["models"]["judge_b"] = dict(provider="fake", model="synthetic-judge-b")
    data["privacy"]["approved_providers"] = ["fake"]
    return data


def write_config(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_config(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    config = load_config(write_config(tmp_path, valid_data))
    assert config.model_dump(mode="json") == valid_data | {
        "roles": {key: {"persona_prompt": None, **value} for key, value in valid_data["roles"].items()}
    }
    assert MAX_ROUNDS == 2
    assert "max_rounds" not in type(config).model_fields


@pytest.mark.parametrize("role", ["specialist", "chair", "red_team", "judge_a", "judge_b"])
def test_each_provider_must_be_approved(tmp_path: Path, valid_data: dict[str, Any], role: str) -> None:
    # The provider guard is tested independently of model-sharing constraints.
    from council.config import validate_models
    config = load_config(write_config(tmp_path, valid_data))
    config.models = config.models.model_copy(deep=True)
    choice = getattr(config.models, role)
    choice.provider = "unapproved"
    if role in ("specialist", "chair"):
        config.models.specialist.provider = config.models.chair.provider = "unapproved"
    if role in ("judge_a", "judge_b"):
        config.models.judge_a.provider = config.models.judge_b.provider = "unapproved"
    with pytest.raises(ConfigError, match="privacy.approved_providers"):
        validate_models(config)


@pytest.mark.parametrize("field,value", [
    ("synthetic_marker", ""), ("synthetic_marker", "  "), ("synthetic_marker", 1),
    ("approved_providers", []), ("approved_providers", ["FAKE"]),
    ("approved_providers", [""]), ("approved_providers", [" fake "]),
    ("approved_providers", ["fake", ""]), ("approved_providers", ["fake", " padded "]),
    ("approved_providers", "fake"), ("approved_providers", [1]),
])
def test_invalid_privacy_config(tmp_path: Path, valid_data: dict[str, Any], field: str, value: object) -> None:
    valid_data["privacy"][field] = value
    with pytest.raises(ConfigError, match="privacy"):
        load_config(write_config(tmp_path, valid_data))


def test_privacy_section_required(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    del valid_data["privacy"]
    with pytest.raises(ConfigError, match="privacy"):
        load_config(write_config(tmp_path, valid_data))


@pytest.mark.parametrize("value", [2, 3])
def test_max_rounds_is_not_a_setting(tmp_path: Path, valid_data: dict[str, Any], value: int) -> None:
    valid_data["max_rounds"] = value
    with pytest.raises(ConfigError, match="max_rounds"):
        load_config(write_config(tmp_path, valid_data))


@pytest.mark.parametrize("text", ["", "[]", "abc", "models: [", "a: 1\na: 2", "!!python/object:builtins.object {}"])
def test_invalid_yaml(tmp_path: Path, text: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_duplicate_key_in_valid_config(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    path = write_config(tmp_path, valid_data)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(yaml.safe_dump({"paths": valid_data["paths"]}))
    with pytest.raises(ConfigError, match="duplicate YAML setting"):
        load_config(path)


@pytest.mark.parametrize("path,value", [
    ("budget.max_calls", "40"), ("budget.max_calls", True), ("budget.max_calls", 1.5),
    ("budget.max_calls", 0), ("budget.max_seconds_total", -1), ("budget.max_total_tokens", 0),
    ("budget.max_tokens_per_call.judge", 0), ("budget.chair_reserve.tokens", 200000),
    ("budget.chair_reserve.tokens", 2999), ("budget.chair_reserve.seconds", 3600),
    ("budget.chair_reserve.calls", 0), ("retries.max_repair_retries_per_turn", 2),
    ("retries.max_api_attempts", 3), ("retries.api_retry_wait_seconds", -1),
    ("retrieval.top_k", 4), ("grounding.quote_words_min", 3), ("grounding.quote_words_max", 41),
    ("judging.disagreement_gap", 3), ("judging.feedback_max_notes", 6), ("judging.feedback_max_words", 41),
    ("temperature.specialist", -0.1), ("temperature.chair", float("nan")),
    ("retrieval.case_sections", ["CASE-unknown"]), ("paths.runs", " "),
    ("roles.SURG.name", ""), ("roles.SURG.kb", ""), ("roles.SURG.keywords", []),
    ("roles.SURG.persona_prompt", None), ("models.specialist.provider", "TBD"),
    ("models.specialist.model", " "), ("models.chair.model", "other"),
    ("models.judge_b.model", "synthetic-judge-a"), ("budget.unknown", 1),
    ("injection_scoring.weights.instruction_override", -1),
    ("injection_scoring.threshold.default", 0), ("injection_scoring.threshold.chair", 0),
    ("injection_scoring.threshold.chair", 1),  # below default (rule 29: chair must be the looser one)
])
def test_bad_value_has_field_path(tmp_path: Path, valid_data: dict[str, Any], path: str, value: object) -> None:
    keys = path.split(".")
    target = valid_data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    with pytest.raises(ConfigError, match=path):
        load_config(write_config(tmp_path, valid_data))


@pytest.mark.parametrize("judge", ["judge_a", "judge_b"])
def test_each_judge_differs_from_specialists(
    tmp_path: Path, valid_data: dict[str, Any], judge: str,
) -> None:
    valid_data["models"][judge] = deepcopy(valid_data["models"]["specialist"])
    with pytest.raises(ConfigError, match="different model"):
        load_config(write_config(tmp_path, valid_data))


def test_required_roles(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    del valid_data["roles"]["RED"]
    with pytest.raises(ConfigError, match="roles"):
        load_config(write_config(tmp_path, valid_data))


def test_unknown_role(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    valid_data["roles"]["UNKNOWN"] = valid_data["roles"].pop("RED")
    with pytest.raises(ConfigError, match="unknown role"):
        load_config(write_config(tmp_path, valid_data))


def test_checked_in_config_has_real_models_and_approved_provider() -> None:
    config = load_config()
    for role_choice in (config.models.specialist, config.models.chair, config.models.red_team,
                       config.models.judge_a, config.models.judge_b):
        assert role_choice.provider != "TBD"
        assert role_choice.model != "TBD"
    assert config.privacy.approved_providers
    assert config.privacy.approved_providers == ["openrouter"]
    assert config.models.judge_a.model != config.models.judge_b.model


def test_tunable_values_and_missing_resource_files(tmp_path: Path, valid_data: dict[str, Any]) -> None:
    valid_data["budget"]["max_total_tokens"] = 150000
    valid_data["budget"]["max_calls"] = 30
    valid_data["budget"]["max_seconds_total"] = 500
    valid_data["temperature"]["specialist"] = 0.0
    valid_data["paths"]["prompts"] = "not-written-yet"
    assert load_config(write_config(tmp_path, valid_data)).budget.max_calls == 30
