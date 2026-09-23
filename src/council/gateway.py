"""The single path from agent code to a model, for decision support requiring clinical sign-off.

Every model call goes through `LLMGateway.call()`. For each call it: checks
privacy (approved provider, no identifier pattern in the prompt), checks the
budget, picks the model and temperature for the role, retries timeouts and
rate limits up to the configured attempt limit, and writes one trace event
per attempt (plus one for a privacy or budget refusal, before any attempt is
made). Agents never import a provider; this is the only caller.
"""

from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Callable

from council.budget import Budget, BudgetExhausted, Reservation
from council.models import Config, EventType, ModelChoice, Role, Round, Step, TraceEvent
from council.privacy import scan_identifiers
from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderTimeout
from council.trace import TraceWriter

SPECIALIST_ROLES = frozenset({Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN})
JUDGE_ROLES = frozenset({Role.JUDGE_A, Role.JUDGE_B})
RETRYABLE_ERRORS = (ProviderTimeout, ProviderRateLimit)


class GatewayRefusal(RuntimeError):
    """No usable output was produced. The caller's turn counts as failed."""


@dataclass(frozen=True)
class GatewayResult:
    raw_output: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int


def estimate_tokens_in(prompt: str) -> int:
    """A safe upper bound on the input token count, used only to size the reservation.

    No tokenizer is available (AGENTS.md keeps dependencies minimal), and
    `Budget.complete` requires actual usage to fall within the reservation
    (budget.py's settlement bound). A real tokenizer never produces more
    tokens than there are characters, so the character count is always a
    safe, if loose, bound; the reservation over-reserves briefly and
    `Budget.complete` releases the unused room once real usage is known.
    """
    return max(1, len(prompt))


def model_choice_for(config: Config, role: Role) -> ModelChoice:
    if role in SPECIALIST_ROLES:
        return config.models.specialist
    if role is Role.CHAIR:
        return config.models.chair
    if role is Role.RED:
        return config.models.red_team
    if role in JUDGE_ROLES:
        return config.models.judge_a if role is Role.JUDGE_A else config.models.judge_b
    raise ValueError(f"no model configured for role {role!r}")


def temperature_for(config: Config, role: Role) -> float:
    if role in SPECIALIST_ROLES:
        return config.temperature.specialist
    if role in JUDGE_ROLES:
        return config.temperature.judge
    if role is Role.RED:
        return config.temperature.red_team
    if role is Role.CHAIR:
        return config.temperature.chair
    raise ValueError(f"no temperature configured for role {role!r}")


def _elapsed_ms(start: float) -> int:
    return max(0, round((perf_counter() - start) * 1000))


class LLMGateway:
    """One shared instance per run. `providers` maps a config provider name to an adapter."""

    def __init__(self, config: Config, budget: Budget, trace: TraceWriter,
                 providers: dict[str, Provider], sleep_fn: Callable[[float], None] = sleep) -> None:
        for role, choice in config.models.model_dump().items():
            if choice["provider"] not in providers:
                raise ValueError(f"no provider registered for models.{role}.provider={choice['provider']!r}")
        self._config = config
        self._budget = budget
        self._trace = trace
        self._providers = providers
        self._sleep = sleep_fn

    def call(self, *, role: Role, step: Step, round_number: Round | None, prompt: str,
             repair: bool = False, retrieved_passage_ids: list[str] | None = None) -> GatewayResult:
        role = Role(role)
        choice = model_choice_for(self._config, role)
        model_label = f"{choice.provider}/{choice.model}"

        self._refuse_if_privacy_blocked(role=role, step=step, round_number=round_number,
                                        repair=repair, provider=choice.provider,
                                        prompt=prompt, model_label=model_label)

        provider = self._providers[choice.provider]
        cap = self._budget.output_cap(role)
        tokens_in = estimate_tokens_in(prompt)
        temperature = temperature_for(self._config, role)
        max_attempts = self._config.retries.max_api_attempts
        last_error = "no attempt was made"

        for attempt in range(1, max_attempts + 1):
            reservation = self._reserve_or_refuse(role=role, step=step, round_number=round_number,
                                                   repair=repair, model_label=model_label,
                                                   tokens_in=tokens_in, cap=cap, attempt=attempt)
            start = perf_counter()
            try:
                response = provider.complete(model=choice.model, prompt=prompt,
                                             max_tokens=cap, temperature=temperature)
            except ProviderError as error:
                latency_ms = _elapsed_ms(start)
                last_error = str(error)
                self._trace.write(TraceEvent(
                    run_id="", seq=0, timestamp="", step=step, event_type=EventType.LLM_CALL,
                    role=role, round=round_number, model=model_label, prompt=prompt,
                    retrieved_passage_ids=retrieved_passage_ids, raw_output=None, parsed_ref=None,
                    tokens_in=None, tokens_out=None, latency_ms=latency_ms, attempt=attempt,
                    repair=repair, budget_tokens_used=self._budget.snapshot().tokens_used, error=last_error,
                ))
                if isinstance(error, RETRYABLE_ERRORS) and attempt < max_attempts:
                    self._sleep(self._config.retries.api_retry_wait_seconds)
                    continue
                raise GatewayRefusal(last_error) from error
            else:
                latency_ms = response.latency_ms
                state = self._budget.complete(reservation, response.tokens_in, response.tokens_out)
                self._trace.write(TraceEvent(
                    run_id="", seq=0, timestamp="", step=step, event_type=EventType.LLM_CALL,
                    role=role, round=round_number, model=model_label, prompt=prompt,
                    retrieved_passage_ids=retrieved_passage_ids, raw_output=response.raw_output,
                    parsed_ref=None, tokens_in=response.tokens_in, tokens_out=response.tokens_out,
                    latency_ms=latency_ms, attempt=attempt, repair=repair,
                    budget_tokens_used=state.tokens_used, error=None,
                ))
                return GatewayResult(response.raw_output, response.tokens_in, response.tokens_out,
                                     model_label, latency_ms)
        raise GatewayRefusal(last_error)

    def write_validation_event(self, *, role: Role, step: Step, round_number: Round | None,
                               parsed_ref: str, note: str) -> None:
        """Record a code-side validation outcome, not a model call (for example T12's rule 24
        override: a claim both judges flagged that a specialist kept anyway, dropped by code).
        """
        self._trace.write(TraceEvent(
            run_id="", seq=0, timestamp="", step=step, event_type=EventType.VALIDATION,
            role=role, round=round_number, model=None, prompt=None, retrieved_passage_ids=None,
            raw_output=None, parsed_ref=parsed_ref, tokens_in=None, tokens_out=None, latency_ms=None,
            attempt=1, repair=False, budget_tokens_used=self._budget.snapshot().tokens_used, error=note,
        ))

    def _refuse_if_privacy_blocked(self, *, role: Role, step: Step, round_number: Round | None,
                                   repair: bool, provider: str, prompt: str, model_label: str) -> None:
        """Contracts rule 20: provider approval and the identifier scan, before the budget check."""
        if provider not in self._config.privacy.approved_providers:
            reason = "provider not approved"
        else:
            hits = scan_identifiers(prompt)
            reason = f"identifier: {hits[0].kind}" if hits else None
        if reason is None:
            return
        self._trace.write(TraceEvent(
            run_id="", seq=0, timestamp="", step=step, event_type=EventType.PRIVACY_BLOCK,
            role=role, round=round_number, model=model_label, prompt=None, retrieved_passage_ids=None,
            raw_output=None, parsed_ref=None, tokens_in=None, tokens_out=None, latency_ms=None,
            attempt=1, repair=repair, budget_tokens_used=self._budget.snapshot().tokens_used, error=reason,
        ))
        raise GatewayRefusal(reason)

    def _reserve_or_refuse(self, *, role: Role, step: Step, round_number: Round | None, repair: bool,
                           model_label: str, tokens_in: int, cap: int, attempt: int) -> Reservation:
        try:
            return self._budget.check_and_reserve(role, tokens_in, cap)
        except BudgetExhausted as error:
            self._trace.write(TraceEvent(
                run_id="", seq=0, timestamp="", step=step, event_type=EventType.BUDGET,
                role=role, round=round_number, model=model_label, prompt=None, retrieved_passage_ids=None,
                raw_output=None, parsed_ref=None, tokens_in=None, tokens_out=None, latency_ms=None,
                attempt=attempt, repair=repair, budget_tokens_used=self._budget.snapshot().tokens_used,
                error=str(error),
            ))
            raise GatewayRefusal(str(error)) from error
