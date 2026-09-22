"""Synthetic budget accounting; no model or provider calls."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from council.budget import Budget, BudgetExhausted, Reservation
from council.models import BudgetConfig, Role


def settings() -> BudgetConfig:
    return BudgetConfig(max_total_tokens=100, max_calls=10, max_seconds_total=100,
                        chair_reserve=dict(tokens=20, calls=2, seconds=20),
                        max_tokens_per_call=dict(specialist=10, judge=12, red_team=15, chair=20))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_initial_state_config_and_snapshot_are_isolated() -> None:
    config, clock = settings(), Clock()
    budget = Budget(config, clock)
    assert budget.snapshot().model_dump() == dict(tokens_used=0, calls_used=0,
                                                started_at=1000, exhausted=False, reason=None)
    config.max_total_tokens = 1
    snapshot = budget.snapshot()
    snapshot.tokens_used = 100
    budget.check_and_reserve(Role.SURG, 1)
    assert budget.snapshot().tokens_used == 0
    assert budget.snapshot().calls_used == 1


@pytest.mark.parametrize("role,cap", [("SURG", 10), ("PHYS", 10), ("ANAES", 10), ("ADMIN", 10),
                                      ("JUDGE_A", 12), ("JUDGE_B", 12), ("RED", 15), ("CHAIR", 20)])
def test_role_output_caps(role: str, cap: int) -> None:
    budget = Budget(settings())
    assert budget.output_cap(Role(role)) == cap
    ticket = budget.check_and_reserve(Role(role), 0)
    assert ticket.max_tokens_out == cap
    with pytest.raises(ValueError, match="per-call cap"):
        budget.check_and_reserve(Role(role), 0, cap + 1)


@pytest.mark.parametrize("role", [role for role in Role if role != Role.CHAIR])
def test_only_chair_can_spend_token_reserve(role: Role) -> None:
    budget = Budget(settings())
    ticket = budget.check_and_reserve(role, 80 - budget.output_cap(role))
    budget.complete(ticket, ticket.tokens_in, ticket.max_tokens_out)
    assert budget.snapshot().tokens_used == 80
    with pytest.raises(BudgetExhausted, match="token budget"):
        budget.check_and_reserve(role, 0, 1)
    chair = budget.check_and_reserve(Role.CHAIR, 0)
    state = budget.complete(chair, 0, 20)
    assert state.tokens_used == 100 and state.exhausted
    with pytest.raises(BudgetExhausted, match="token budget"):
        budget.check_and_reserve(Role.CHAIR, 0, 1)


def test_pending_reservations_prevent_oversubscription() -> None:
    budget = Budget(settings())
    budget.check_and_reserve(Role.SURG, 60)  # 70 held, zero settled
    assert budget.snapshot().tokens_used == 0
    with pytest.raises(BudgetExhausted, match="token budget"):
        budget.check_and_reserve(Role.PHYS, 1)  # 11 would exceed non-chair 80
    state = budget.snapshot()
    assert state.calls_used == 1 and state.tokens_used == 0
    assert state.exhausted and state.reason == "token budget exhausted"


def test_settlement_releases_unused_room_and_counts_both_token_directions() -> None:
    budget = Budget(settings())
    ticket = budget.check_and_reserve(Role.SURG, 60)
    state = budget.complete(ticket, 3, 4)
    assert state.tokens_used == 7 and state.calls_used == 1
    state.tokens_used = 99
    another = budget.check_and_reserve(Role.PHYS, 60)
    budget.complete(another, 2, 5)
    assert budget.snapshot().tokens_used == 14


def test_call_limit_counts_every_attempt_even_zero_usage_failures() -> None:
    budget = Budget(settings())
    for _ in range(8):
        ticket = budget.check_and_reserve(Role.SURG, 0, 0)
        budget.complete(ticket, 0, 0)
    with pytest.raises(BudgetExhausted, match="call budget"):
        budget.check_and_reserve(Role.SURG, 0, 0)
    for _ in range(2):
        ticket = budget.check_and_reserve(Role.CHAIR, 0, 0)
        budget.complete(ticket, 0, 0)
    with pytest.raises(BudgetExhausted, match="call budget"):
        budget.check_and_reserve(Role.CHAIR, 0, 0)
    assert budget.snapshot().calls_used == 10 and budget.snapshot().tokens_used == 0


def test_time_limits_and_chair_reserve_use_elapsed_time() -> None:
    clock = Clock()
    budget = Budget(settings(), clock)
    clock.now += 79
    ticket = budget.check_and_reserve(Role.SURG, 0)
    assert ticket.seconds_remaining == 1
    clock.now += 1
    with pytest.raises(BudgetExhausted, match="time budget"):
        budget.check_and_reserve(Role.SURG, 0)
    chair = budget.check_and_reserve(Role.CHAIR, 0)
    assert chair.seconds_remaining == 20
    clock.now += 20
    with pytest.raises(BudgetExhausted, match="time budget"):
        budget.check_and_reserve(Role.CHAIR, 0)
    state = budget.snapshot()
    assert state.started_at == 1000 and state.reason == "time budget exhausted"


def test_exhaustion_stays_visible_and_stops_other_roles() -> None:
    budget = Budget(settings())
    with pytest.raises(BudgetExhausted):
        budget.check_and_reserve(Role.SURG, 90)
    with pytest.raises(BudgetExhausted):
        budget.check_and_reserve(Role.ADMIN, 0, 0)
    ticket = budget.check_and_reserve(Role.CHAIR, 0)
    assert budget.complete(ticket, 0, 1).exhausted


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_invalid_token_counts_never_change_state(value: int) -> None:
    budget = Budget(settings())
    before = budget.snapshot()
    with pytest.raises(ValueError, match="nonnegative integers"):
        budget.check_and_reserve(Role.SURG, value)
    with pytest.raises(ValueError, match="nonnegative integers"):
        budget.check_and_reserve(Role.SURG, 0, value)
    assert budget.snapshot() == before
    ticket = budget.check_and_reserve(Role.SURG, 5)
    for incoming, outgoing in [(value, 0), (0, value)]:
        with pytest.raises(ValueError, match="nonnegative integers"):
            budget.complete(ticket, incoming, outgoing)
    assert budget.snapshot().tokens_used == 0


def test_unknown_role_cannot_get_chair_privileges() -> None:
    with pytest.raises(ValueError):
        Budget(settings()).check_and_reserve("NOT_A_ROLE", 0)


def test_settlement_rejects_unknown_duplicate_and_over_bound_usage() -> None:
    budget = Budget(settings())
    ticket = budget.check_and_reserve(Role.SURG, 5)
    for incoming, outgoing in [(6, 0), (0, 11)]:
        with pytest.raises(ValueError, match="reserved bounds"):
            budget.complete(ticket, incoming, outgoing)
    forged = Reservation(ticket.tokens_in, ticket.max_tokens_out, ticket.seconds_remaining)
    with pytest.raises(ValueError, match="unknown or already"):
        budget.complete(forged, 1, 1)
    foreign = Budget(settings()).check_and_reserve(Role.SURG, 5)
    with pytest.raises(ValueError, match="unknown or already"):
        budget.complete(foreign, 1, 1)
    assert budget.complete(ticket, 2, 3).tokens_used == 5
    with pytest.raises(ValueError, match="unknown or already"):
        budget.complete(ticket, 2, 3)
    assert budget.snapshot().tokens_used == 5


def test_parallel_admission_cannot_overspend_remaining_tokens() -> None:
    budget, barrier = Budget(settings()), Barrier(32)
    def attempt(_: int) -> bool:
        barrier.wait(timeout=10)
        try:
            budget.check_and_reserve(Role.SURG, 0)
        except BudgetExhausted:
            return False
        return True
    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(attempt, range(32)))
    assert sum(accepted) == 8
    assert budget.snapshot().calls_used == 8


def test_parallel_same_reservation_is_settled_once() -> None:
    budget, barrier = Budget(settings()), Barrier(32)
    ticket = budget.check_and_reserve(Role.SURG, 5)
    def settle(_: int) -> bool:
        barrier.wait(timeout=10)
        try:
            budget.complete(ticket, 2, 3)
        except ValueError:
            return False
        return True
    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(settle, range(32)))
    assert sum(accepted) == 1
    assert budget.snapshot().tokens_used == 5
    assert budget.snapshot().calls_used == 1


@pytest.mark.parametrize("operation", ["reserve", "complete", "snapshot"])
def test_budget_operations_wait_for_shared_lock(operation: str) -> None:
    budget, entered = Budget(settings()), Event()
    ticket = budget.check_and_reserve(Role.SURG, 1)
    def work() -> None:
        entered.set()
        if operation == "reserve":
            budget.check_and_reserve(Role.PHYS, 1)
        elif operation == "complete":
            budget.complete(ticket, 1, 1)
        else:
            budget.snapshot()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with budget._lock:
            future = pool.submit(work)
            assert entered.wait(timeout=5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
        future.result(timeout=5)
