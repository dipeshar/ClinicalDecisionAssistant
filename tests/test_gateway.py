"""LLMGateway: privacy, budget, model/temperature choice, API retry, and one trace event per attempt."""

import ast
import json
from pathlib import Path
import sys

import pytest

from council.budget import Budget
from council.gateway import GatewayRefusal, LLMGateway, model_choice_for, temperature_for
from council.models import BudgetConfig, Config, Role, Step
from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderResponse, ProviderTimeout
from council.providers.fake import FakeProvider, Scripted
from council.trace import TraceWriter


def tiny_budget() -> Budget:
    return Budget(BudgetConfig(
        max_total_tokens=5, max_calls=5, max_seconds_total=60,
        chair_reserve=dict(tokens=1, calls=1, seconds=10),
        max_tokens_per_call=dict(specialist=5, judge=5, red_team=5, chair=5),
    ))


def make_gateway(config: Config, tmp_path: Path, providers: dict[str, Provider], *,
                 budget: Budget | None = None, sleep_fn=lambda seconds: None) -> tuple[LLMGateway, Path]:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceWriter(trace_path, "run-gateway-synthetic")
    gateway = LLMGateway(config, budget or Budget(config.budget), trace, providers, sleep_fn=sleep_fn)
    return gateway, trace_path


def read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_successful_call_returns_output_and_writes_one_llm_call_event(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted(raw_output='{"ok": true}', tokens_in=3, tokens_out=4, latency_ms=7)])
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider})
    result = gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="Synthetic prompt")
    assert result.raw_output == '{"ok": true}'
    assert (result.tokens_in, result.tokens_out, result.latency_ms) == (3, 4, 7)
    assert result.model == "fake/specialist"
    events = read_events(trace_path)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "llm_call" and event["attempt"] == 1 and event["repair"] is False
    assert event["error"] is None and event["role"] == "SURG" and event["round"] == 1
    assert event["prompt"] == "Synthetic prompt" and event["raw_output"] == '{"ok": true}'
    assert (event["tokens_in"], event["tokens_out"], event["latency_ms"]) == (3, 4, 7)
    assert event["budget_tokens_used"] == 7
    assert provider.calls_made == 1


def test_bad_json_output_is_returned_as_is_grounding_is_not_gateways_job(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted(raw_output="not valid json {{{")])
    gateway, _ = make_gateway(config, tmp_path, {"fake": provider})
    result = gateway.call(role=Role.PHYS, step=Step.SPECIALIST, round_number=1, prompt="p")
    assert result.raw_output == "not valid json {{{"


def test_privacy_blocks_unapproved_provider_before_any_attempt(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted()])
    config = config.model_copy(deep=True)
    config.privacy.approved_providers = []
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider})
    with pytest.raises(GatewayRefusal, match="not approved"):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    events = read_events(trace_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "privacy_block" and events[0]["prompt"] is None
    assert provider.calls_made == 0


def test_privacy_blocks_prompt_matching_identifier_pattern_without_leaking_it(
    config: Config, tmp_path: Path,
) -> None:
    provider = FakeProvider("fake", [Scripted()])
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider})
    prompt = "Contact patient at synthetic.demo.patient@example.com for follow-up"
    with pytest.raises(GatewayRefusal, match="identifier"):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt=prompt)
    events = read_events(trace_path)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "privacy_block" and event["error"] == "identifier: email"
    assert event["prompt"] is None
    raw_line = trace_path.read_text(encoding="utf-8")
    assert "synthetic.demo.patient@example.com" not in raw_line
    assert provider.calls_made == 0


def test_privacy_check_runs_before_the_budget_check(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted()])
    budget = tiny_budget()
    config = config.model_copy(deep=True)
    config.privacy.approved_providers = []
    gateway, _ = make_gateway(config, tmp_path, {"fake": provider}, budget=budget)
    with pytest.raises(GatewayRefusal, match="not approved"):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    assert budget.snapshot().calls_used == 0


def test_tiny_budget_refuses_the_call_and_writes_one_budget_event(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted()])
    budget = tiny_budget()
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, budget=budget)
    with pytest.raises(GatewayRefusal, match="token budget"):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    events = read_events(trace_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "budget" and events[0]["prompt"] is None
    assert provider.calls_made == 0


def test_reservation_accounts_for_prompt_length_not_just_the_output_cap(config: Config, tmp_path: Path) -> None:
    """A budget tight enough to admit the output cap alone, but not the cap plus a long prompt."""
    budget = Budget(BudgetConfig(
        max_total_tokens=15, max_calls=5, max_seconds_total=60,
        chair_reserve=dict(tokens=1, calls=1, seconds=10),
        max_tokens_per_call=dict(specialist=10, judge=10, red_team=10, chair=10),
    ))
    provider = FakeProvider("fake", [Scripted()])
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, budget=budget)
    with pytest.raises(GatewayRefusal, match="token budget"):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="x" * 10)
    assert provider.calls_made == 0


def test_timeout_retries_once_then_succeeds(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [ProviderTimeout, Scripted(raw_output="ok", tokens_in=1, tokens_out=2)])
    sleeps: list[float] = []
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, sleep_fn=sleeps.append)
    result = gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    assert result.raw_output == "ok"
    events = read_events(trace_path)
    assert [event["attempt"] for event in events] == [1, 2]
    assert events[0]["event_type"] == "llm_call" and events[0]["error"] is not None
    assert events[1]["error"] is None
    assert sleeps == [config.retries.api_retry_wait_seconds]


def test_rate_limit_retries_once_then_succeeds(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [ProviderRateLimit, Scripted(raw_output="ok", tokens_in=1, tokens_out=2)])
    sleeps: list[float] = []
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, sleep_fn=sleeps.append)
    result = gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    assert result.raw_output == "ok"
    events = read_events(trace_path)
    assert [event["attempt"] for event in events] == [1, 2]
    assert sleeps == [config.retries.api_retry_wait_seconds]


def test_timeout_twice_exhausts_attempts_and_refuses(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [ProviderTimeout, ProviderTimeout])
    sleeps: list[float] = []
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, sleep_fn=sleeps.append)
    with pytest.raises(GatewayRefusal):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    events = read_events(trace_path)
    assert [event["attempt"] for event in events] == [1, 2]
    assert len(sleeps) == 1


def test_non_timeout_provider_error_does_not_retry(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [ProviderError, Scripted()])
    sleeps: list[float] = []
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider}, sleep_fn=sleeps.append)
    with pytest.raises(GatewayRefusal):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    events = read_events(trace_path)
    assert len(events) == 1 and events[0]["attempt"] == 1
    assert sleeps == []
    assert provider.calls_made == 1


def test_every_attempt_counts_against_the_budget(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [ProviderTimeout, Scripted(tokens_in=1, tokens_out=1)])
    budget = Budget(config.budget)
    gateway, _ = make_gateway(config, tmp_path, {"fake": provider}, budget=budget, sleep_fn=lambda s: None)
    gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    assert budget.snapshot().calls_used == 2


def test_model_choice_for_maps_each_role_to_its_own_config_field(config: Config) -> None:
    for role, expected in [
        (Role.SURG, config.models.specialist), (Role.PHYS, config.models.specialist),
        (Role.ANAES, config.models.specialist), (Role.ADMIN, config.models.specialist),
        (Role.CHAIR, config.models.chair), (Role.RED, config.models.red_team),
        (Role.JUDGE_A, config.models.judge_a), (Role.JUDGE_B, config.models.judge_b),
    ]:
        assert model_choice_for(config, role) is expected


def test_temperature_for_maps_each_role_to_its_own_config_field(config: Config) -> None:
    for role, expected in [
        (Role.SURG, config.temperature.specialist), (Role.PHYS, config.temperature.specialist),
        (Role.ANAES, config.temperature.specialist), (Role.ADMIN, config.temperature.specialist),
        (Role.JUDGE_A, config.temperature.judge), (Role.JUDGE_B, config.temperature.judge),
        (Role.RED, config.temperature.red_team), (Role.CHAIR, config.temperature.chair),
    ]:
        assert temperature_for(config, role) == expected


def test_role_selects_configured_model_and_temperature(config: Config, tmp_path: Path) -> None:
    captured: list[tuple[str, float]] = []

    class SpyProvider(Provider):
        name = "fake"

        def complete(self, *, model: str, prompt: str, max_tokens: int, temperature: float) -> ProviderResponse:
            captured.append((model, temperature))
            return ProviderResponse("{}", 1, 1, 1)

    gateway, _ = make_gateway(config, tmp_path, {"fake": SpyProvider()})
    for role in (Role.SURG, Role.JUDGE_A, Role.JUDGE_B, Role.RED, Role.CHAIR):
        gateway.call(role=role, step=Step.SPECIALIST, round_number=None, prompt="p")
    assert captured == [
        ("specialist", config.temperature.specialist),
        ("judge", config.temperature.judge),
        ("judge", config.temperature.judge),
        ("specialist", config.temperature.red_team),
        ("specialist", config.temperature.chair),
    ]


def test_gateway_construction_requires_a_provider_for_every_configured_role(config: Config, tmp_path: Path) -> None:
    trace = TraceWriter(tmp_path / "trace.jsonl", "run-synthetic")
    with pytest.raises(ValueError, match="no provider registered"):
        LLMGateway(config, Budget(config.budget), trace, providers={})


def test_output_cap_is_enforced_on_the_reservation_not_just_the_provider(config: Config, tmp_path: Path) -> None:
    provider = FakeProvider("fake", [Scripted(tokens_out=config.budget.max_tokens_per_call.specialist + 1)])
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider})
    with pytest.raises(GatewayRefusal):
        gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="p")
    events = read_events(trace_path)
    assert events[0]["error"] is not None


def test_no_module_outside_providers_imports_a_provider_sdk() -> None:
    """A real import-graph check: only providers/ may import anything beyond the stdlib and our own deps."""
    src_root = Path(__file__).resolve().parents[1] / "src" / "council"
    allowed_top_level = set(sys.stdlib_module_names) | {"pydantic", "yaml", "rank_bm25", "council"}
    violations: list[str] = []
    for path in src_root.rglob("*.py"):
        relative = path.relative_to(src_root)
        if relative.parts[0] == "providers" or "__pycache__" in relative.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            violations.extend(f"{relative}: imports {name!r}" for name in names if name not in allowed_top_level)
    assert violations == []


def test_api_keys_never_appear_in_trace_or_run_bundle(
    config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contracts rule 21: API keys never appear in trace.jsonl, run.json or any report."""
    fake_key = "sk-synthetic-fake-key-9f3c7a21e8"
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", fake_key)

    class KeyHoldingProvider(Provider):
        """Stands in for a real adapter (T17) that reads its key from the environment."""

        name = "fake"

        def __init__(self, api_key: str) -> None:
            self._api_key = api_key  # held, never returned or logged

        def complete(self, *, model: str, prompt: str, max_tokens: int, temperature: float) -> ProviderResponse:
            if not self._api_key:
                raise ProviderError("missing credentials")
            return ProviderResponse('{"ok": true}', 2, 2, 1)

    import os
    provider = KeyHoldingProvider(os.environ["FAKE_PROVIDER_API_KEY"])
    gateway, trace_path = make_gateway(config, tmp_path, {"fake": provider})
    gateway.call(role=Role.SURG, step=Step.SPECIALIST, round_number=1, prompt="Synthetic prompt")

    raw_trace = trace_path.read_bytes()
    assert fake_key.encode() not in raw_trace

    run_bundle_like = json.dumps({
        "config_snapshot": config.model_dump(mode="json"),
        "trace_events": read_events(trace_path),
    })
    assert fake_key not in run_bundle_like
