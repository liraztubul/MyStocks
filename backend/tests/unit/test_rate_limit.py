from app.core import rate_limit
from app.core.rate_limit import Limit, RateLimiter

LIMIT = Limit(attempts=3, window_seconds=60)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def limiter_with_clock() -> tuple[RateLimiter, Clock]:
    clock = Clock()
    return RateLimiter(timer=clock), clock


def test_under_the_limit_is_allowed() -> None:
    limiter, _ = limiter_with_clock()
    for _ in range(2):
        limiter.record("ip")
    assert limiter.retry_after("ip", LIMIT) is None


def test_at_the_limit_reports_seconds_until_oldest_attempt_expires() -> None:
    limiter, clock = limiter_with_clock()
    for _ in range(3):
        limiter.record("ip")
        clock.now += 10
    # Oldest attempt at t=1000 expires at t=1060; now is t=1030.
    assert limiter.retry_after("ip", LIMIT) == 30


def test_window_slides() -> None:
    limiter, clock = limiter_with_clock()
    for _ in range(3):
        limiter.record("ip")
    clock.now += 60
    assert limiter.retry_after("ip", LIMIT) is None


def test_keys_are_independent() -> None:
    limiter, _ = limiter_with_clock()
    for _ in range(3):
        limiter.record(("login", "1.1.1.1"))
    assert limiter.retry_after(("login", "1.1.1.1"), LIMIT) is not None
    assert limiter.retry_after(("login", "2.2.2.2"), LIMIT) is None


def test_reset_clears_everything() -> None:
    limiter, _ = limiter_with_clock()
    for _ in range(3):
        limiter.record("ip")
    limiter.reset()
    assert limiter.retry_after("ip", LIMIT) is None


def test_memory_is_bounded_and_fails_open(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(rate_limit, "MAX_TRACKED_KEYS", 3)
    limiter, _ = limiter_with_clock()
    for _ in range(3):
        limiter.record("victim")
    limiter.record("a")
    limiter.record("b")
    limiter.record("c")  # fourth distinct key: the table is cleared rather than growing
    assert limiter.retry_after("victim", LIMIT) is None
