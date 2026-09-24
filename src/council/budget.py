"""Locked accounting for synthetic decision support requiring clinical sign-off."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from council.models import BudgetConfig, BudgetState, Role


class BudgetExhausted(RuntimeError):
    """The gateway must refuse this attempt and record the reason."""


@dataclass(frozen=True, eq=False)
class Reservation:
    """One admitted attempt; identity prevents forged or duplicate settlement."""

    tokens_in: int
    max_tokens_out: int
    seconds_remaining: float


def nonnegative_integer(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("token counts must be nonnegative integers")


class Budget:
    """One shared instance per run, constructed from validated config.

    Admission holds a conservative input-token bound plus the output cap.
    Actual token usage is settled once; outstanding reservations also consume
    room, so concurrent attempts cannot spend the same remaining tokens.
    Each API/repair attempt needs its own reservation. Success settles actual
    usage; failure releases the reservation while retaining the attempt count.
    The gateway must enforce seconds_remaining as a timeout and supply usage
    within the reserved bounds. This class does not call providers or retry.
    """

    def __init__(self, config: BudgetConfig, clock: Callable[[], float] = monotonic) -> None:
        self._config = config.model_copy(deep=True)
        self._clock = clock
        self._lock = Lock()
        self._state = BudgetState(tokens_used=0, calls_used=0, started_at=clock(),
                                  exhausted=False, reason=None)
        self._pending: dict[Reservation, int] = {}

    def snapshot(self) -> BudgetState:
        with self._lock:
            return self._state.model_copy(deep=True)

    def output_cap(self, role: Role) -> int:
        role = Role(role)
        if role in (Role.SURG, Role.PHYS, Role.ANAES, Role.ADMIN):
            return self._config.max_tokens_per_call.specialist
        if role in (Role.JUDGE_A, Role.JUDGE_B):
            return self._config.max_tokens_per_call.judge
        if role == Role.RED:
            return self._config.max_tokens_per_call.red_team
        return self._config.max_tokens_per_call.chair

    def check_and_reserve(self, role: Role, tokens_in: int,
                          max_tokens_out: int | None = None) -> Reservation:
        role = Role(role)
        nonnegative_integer(tokens_in)
        cap = self.output_cap(role)
        output = cap if max_tokens_out is None else max_tokens_out
        nonnegative_integer(output)
        if output > cap:
            raise ValueError("requested output exceeds the role's per-call cap")
        with self._lock:
            config = self._config
            chair = role == Role.CHAIR
            if self._state.exhausted and not chair:
                raise BudgetExhausted(f"{self._state.reason}: requested this call, already exhausted (0 remaining)")
            token_limit = config.max_total_tokens - (0 if chair else config.chair_reserve.tokens)
            call_limit = config.max_calls - (0 if chair else config.chair_reserve.calls)
            time_limit = config.max_seconds_total - (0 if chair else config.chair_reserve.seconds)
            remaining = time_limit - (self._clock() - self._state.started_at)
            pending_total = sum(self._pending.values())
            total = tokens_in + output
            reason = None
            detail = None
            if self._state.tokens_used + pending_total + total > token_limit:
                reason = "token budget exhausted"
                tokens_remaining = token_limit - self._state.tokens_used - pending_total
                detail = f"{reason}: requested {total} tokens, {tokens_remaining} remaining"
            elif self._state.calls_used >= call_limit:
                reason = "call budget exhausted"
                detail = f"{reason}: requested 1 call, {call_limit - self._state.calls_used} remaining"
            elif remaining <= 0:
                reason = "time budget exhausted"
                detail = f"{reason}: requested this call, {remaining:.1f}s remaining"
            if reason is not None:
                self._state.exhausted = True
                self._state.reason = reason
                raise BudgetExhausted(detail)
            reservation = Reservation(tokens_in, output, remaining)
            self._pending[reservation] = total
            self._state.calls_used += 1
            return reservation

    def complete(self, reservation: Reservation, tokens_in: int, tokens_out: int) -> BudgetState:
        """Settle known usage, release unused room, retain the attempt count.

        Failed attempts use `release` instead, because reservations represent
        only attempts that are currently in flight.
        """
        nonnegative_integer(tokens_in)
        nonnegative_integer(tokens_out)
        with self._lock:
            if reservation not in self._pending:
                raise ValueError("unknown or already settled reservation")
            if tokens_in > reservation.tokens_in or tokens_out > reservation.max_tokens_out:
                raise ValueError("actual usage exceeds the reserved bounds")
            self._state.tokens_used += tokens_in + tokens_out
            del self._pending[reservation]
            return self._state.model_copy(deep=True)

    def release(self, reservation: Reservation) -> BudgetState:
        """Release a failed attempt's held tokens while retaining its call count."""
        with self._lock:
            if reservation not in self._pending:
                raise ValueError("unknown or already settled reservation")
            del self._pending[reservation]
            return self._state.model_copy(deep=True)
