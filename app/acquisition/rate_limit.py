from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import time


@dataclass
class RateLimitEvent:
    provider: str
    waited_seconds: float


class ProviderRateLimiter:
    def __init__(
        self,
        calls_per_minute: int,
        *,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self.calls_per_minute = max(int(calls_per_minute), 0)
        self.clock = clock
        self.sleeper = sleeper
        self._last_call_at: dict[str, float] = defaultdict(float)

    @property
    def min_interval_seconds(self) -> float:
        if self.calls_per_minute <= 0:
            return 0.0
        return 60.0 / self.calls_per_minute

    def acquire(self, provider: str) -> RateLimitEvent:
        if self.calls_per_minute <= 0:
            self._last_call_at[provider] = self.clock()
            return RateLimitEvent(provider, 0.0)

        now = self.clock()
        if provider not in self._last_call_at:
            self._last_call_at[provider] = now
            return RateLimitEvent(provider, 0.0)
        last = self._last_call_at.get(provider, 0.0)
        elapsed = now - last
        wait_seconds = max(0.0, self.min_interval_seconds - elapsed)
        if wait_seconds > 0:
            self.sleeper(wait_seconds)
        self._last_call_at[provider] = self.clock()
        return RateLimitEvent(provider, wait_seconds)
