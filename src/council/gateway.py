"""The single path from agent code to a model, for decision support requiring clinical sign-off.

Every model call goes through `LLMGateway.call()`. For each call it: checks
privacy (approved provider, no identifier pattern in the prompt), checks the
budget, picks the model and temperature for the role, retries timeouts and
rate limits up to the configured attempt limit, and writes one trace event
per attempt (plus one for a privacy or budget refusal, before any attempt is
made). Agents never import a provider; this is the only caller.
"""

from dataclasses import dataclass
import re
from threading import Lock
from time import perf_counter, sleep
from typing import Callable

from council.budget import Budget, BudgetExhausted, Reservation
from council.models import BudgetState, Config, EventType, ModelChoice, PrivacySummary, Role, Round, Step, TraceEvent
from council.privacy import scan_identifiers
from council.providers.base import Provider, ProviderError, ProviderRateLimit, ProviderTimeout
from council.trace import TraceWriter

SPECIALIST_ROLES = frozenset({Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN})
JUDGE_ROLES = frozenset({Role.JUDGE_A, Role.JUDGE_B})
RETRYABLE_ERRORS = (ProviderTimeout, ProviderRateLimit)
RETRY_AFTER = re.compile(r"(?:^|;\s*)Retry-After:\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.IGNORECASE)
RETRY_AFTER_SAFETY_SECONDS = 0.25


class GatewayRefusal(RuntimeError):
    """No usable output was produced. The caller's turn counts as failed."""


@dataclass(frozen=True)
class GatewayResult:
    raw_output: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int


def estimate_tokens_in(text: str) -> int:
    """A safe upper bound on the input token count, used only to size the reservation.

    No tokenizer is available (AGENTS.md keeps dependencies minimal), and
    `Budget.complete` requires actual usage to fall within the reservation
    (budget.py's settlement bound). A real tokenizer never produces more
    tokens than there are characters, so the character count is always a
    safe, if loose, bound; the reservation over-reserves briefly and
    `Budget.complete` releases the unused room once real usage is known.
    """
    return max(1, len(text))


def combined_for_trace(system: str, user: str) -> str:
    """One string for the trace's single `prompt` field (contracts section 10),
    labeled so the real system/user split sent to the provider stays visible."""
    return f"[SYSTEM]\n{system}\n\n[USER]\n{user}"


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


def reasoning_effort_for(config: Config, role: Role) -> str:
    if role in SPECIALIST_ROLES:
        return config.reasoning_effort.specialist
    if role in JUDGE_ROLES:
        return config.reasoning_effort.judge
    if role is Role.RED:
        return config.reasoning_effort.red_team
    if role is Role.CHAIR:
        return config.reasoning_effort.chair
    raise ValueError(f"no reasoning effort configured for role {role!r}")


def _elapsed_ms(start: float) -> int:
    return max(0, round((perf_counter() - start) * 1000))


def retry_wait_seconds(error: ProviderRateLimit, fallback: float) -> float:
    """Use a numeric Retry-After value plus a small margin, else configured fallback."""
    match = RETRY_AFTER.search(str(error))
    return float(match.group(1)) + RETRY_AFTER_SAFETY_SECONDS if match else fallback


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
        self._provider_lock = Lock()
        self._usage_lock = Lock()
        self._prompts_checked = 0
        self._prompts_blocked = 0
        self._providers_used: set[str] = set()

    def call(self, *, role: Role, step: Step, round_number: Round | None, system: str, user: str,
             repair: bool = False, retrieved_passage_ids: list[str] | None = None) -> GatewayResult:
        role = Role(role)
        choice = model_choice_for(self._config, role)
        model_label = f"{choice.provider}/{choice.model}"
        prompt = combined_for_trace(system, user)

        with self._usage_lock:
            self._prompts_checked += 1

        self._refuse_if_privacy_blocked(role=role, step=step, round_number=round_number,
                                        repair=repair, provider=choice.provider,
                                        system=system, user=user, model_label=model_label)

        provider = self._providers[choice.provider]
        cap = self._budget.output_cap(role)
        tokens_in = estimate_tokens_in(system) + estimate_tokens_in(user)
        temperature = temperature_for(self._config, role)
        reasoning_effort = reasoning_effort_for(self._config, role)
        max_attempts = self._config.retries.max_api_attempts
        last_error = "no attempt was made"

        for attempt in range(1, max_attempts + 1):
            reservation = self._reserve_or_refuse(role=role, step=step, round_number=round_number,
                                                   repair=repair, model_label=model_label,
                                                   tokens_in=tokens_in, cap=cap, attempt=attempt)
            start = perf_counter()
            with self._usage_lock:
                self._providers_used.add(choice.provider)
            failed_state: BudgetState | None = None
            try:
                with self._provider_lock:
                    try:
                        response = provider.complete(
                            model=choice.model, system=system, user=user, max_tokens=cap,
                            temperature=temperature, reasoning_effort=reasoning_effort,
                        )
                    except ProviderError as error:
                        failed_state = self._budget.release(reservation)
                        if isinstance(error, ProviderRateLimit):
                            self._sleep(retry_wait_seconds(
                                error, self._config.retries.api_retry_wait_seconds,
                            ))
                        raise
            except ProviderError as error:
                latency_ms = _elapsed_ms(start)
                last_error = str(error)
                assert failed_state is not None
                self._trace.write(TraceEvent(
                    run_id="", seq=0, timestamp="", step=step, event_type=EventType.LLM_CALL,
                    role=role, round=round_number, model=model_label, prompt=prompt,
                    retrieved_passage_ids=retrieved_passage_ids, raw_output=None, parsed_ref=None,
                    tokens_in=None, tokens_out=None, latency_ms=latency_ms, attempt=attempt,
                    repair=repair, budget_tokens_used=failed_state.tokens_used, error=last_error,
                    finish_reason=None, reasoning=None,
                ))
                if isinstance(error, RETRYABLE_ERRORS) and attempt < max_attempts:
                    if not isinstance(error, ProviderRateLimit):
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
                    finish_reason=response.finish_reason, reasoning=response.reasoning,
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
            finish_reason=None, reasoning=None,
        ))

    def budget_state(self) -> BudgetState:
        """A detached snapshot for orchestration decisions."""
        return self._budget.snapshot()

    def privacy_summary(self) -> PrivacySummary:
        """Code-owned outbound privacy accounting, safe under parallel calls."""
        with self._usage_lock:
            return PrivacySummary(
                synthetic_marker_found=True, ingest_identifier_hits=0,
                outbound_prompts_checked=self._prompts_checked,
                outbound_prompts_blocked=self._prompts_blocked,
                approved_providers=list(self._config.privacy.approved_providers),
                providers_used=sorted(self._providers_used),
            )

    def _refuse_if_privacy_blocked(self, *, role: Role, step: Step, round_number: Round | None,
                                   repair: bool, provider: str, system: str, user: str,
                                   model_label: str) -> None:
        """Contracts rule 20: provider approval and the identifier scan, before the budget check."""
        if provider not in self._config.privacy.approved_providers:
            reason = "provider not approved"
        else:
            hits = scan_identifiers(system) + scan_identifiers(user)
            reason = f"identifier: {hits[0].kind}" if hits else None
        if reason is None:
            return
        with self._usage_lock:
            self._prompts_blocked += 1
        self._trace.write(TraceEvent(
            run_id="", seq=0, timestamp="", step=step, event_type=EventType.PRIVACY_BLOCK,
            role=role, round=round_number, model=model_label, prompt=None, retrieved_passage_ids=None,
            raw_output=None, parsed_ref=None, tokens_in=None, tokens_out=None, latency_ms=None,
            attempt=1, repair=repair, budget_tokens_used=self._budget.snapshot().tokens_used, error=reason,
            finish_reason=None, reasoning=None,
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
                error=str(error), finish_reason=None, reasoning=None,
            ))
            raise GatewayRefusal(str(error)) from error
