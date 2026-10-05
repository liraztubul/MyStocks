"""In-process sliding-window rate limiter.

In memory is enough because the free Render plan runs exactly one instance; the counters reset
whenever that instance spins down, which only ever makes the limits more lenient.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Hashable
from dataclasses import dataclass

MAX_TRACKED_KEYS = 50_000


@dataclass(frozen=True)
class Limit:
    attempts: int
    window_seconds: float


class RateLimiter:
    def __init__(self, timer: Callable[[], float] = time.monotonic) -> None:
        self._timer = timer
        self._hits: dict[Hashable, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: Hashable, limit: Limit, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - limit.window_seconds:
            hits.popleft()
        return hits

    def retry_after(self, key: Hashable, limit: Limit) -> int | None:
        """Seconds until `key` may try again, or None if it's under the limit."""
        with self._lock:
            now = self._timer()
            hits = self._prune(key, limit, now)
            if len(hits) < limit.attempts:
                return None
            return max(1, int(hits[0] + limit.window_seconds - now + 0.999))

    def record(self, key: Hashable) -> None:
        with self._lock:
            # Bound memory against a flood of distinct keys; clearing fails open (more lenient),
            # never closed.
            if len(self._hits) >= MAX_TRACKED_KEYS and key not in self._hits:
                self._hits.clear()
            self._hits[key].append(self._timer())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Per IP: slows credential stuffing. Per (IP, email) failures: slows guessing one account without
# letting a stranger lock its owner out (an email-only key would let anyone do that).
LOGIN_PER_IP = Limit(attempts=10, window_seconds=5 * 60)
LOGIN_FAILURES_PER_IP_AND_EMAIL = Limit(attempts=5, window_seconds=15 * 60)
REGISTER_PER_IP = Limit(attempts=5, window_seconds=60 * 60)

limiter = RateLimiter()
