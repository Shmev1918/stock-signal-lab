from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time


@dataclass(frozen=True)
class PolygonRateLimitEvent:
    endpoint: str
    waited_seconds: float

    @property
    def rate_limited(self) -> bool:
        return self.waited_seconds > 0.0


class PolygonRateLimiter:
    def __init__(
        self,
        requests_per_minute: int = 3,
        *,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self.requests_per_minute = max(int(requests_per_minute), 0)
        self.clock = clock
        self.sleeper = sleeper
        self._lock = Lock()
        self._last_request_at: float | None = None

    @property
    def min_interval_seconds(self) -> float:
        if self.requests_per_minute <= 0:
            return 0.0
        return 60.0 / self.requests_per_minute

    def acquire(self, endpoint: str) -> PolygonRateLimitEvent:
        if self.requests_per_minute <= 0:
            with self._lock:
                self._last_request_at = self.clock()
            return PolygonRateLimitEvent(endpoint=endpoint, waited_seconds=0.0)

        with self._lock:
            now = self.clock()
            if self._last_request_at is None:
                self._last_request_at = now
                return PolygonRateLimitEvent(endpoint=endpoint, waited_seconds=0.0)
            elapsed = now - self._last_request_at
            wait_seconds = max(0.0, self.min_interval_seconds - elapsed)
            if wait_seconds > 0:
                self.sleeper(wait_seconds)
            self._last_request_at = self.clock()
            return PolygonRateLimitEvent(endpoint=endpoint, waited_seconds=wait_seconds)
