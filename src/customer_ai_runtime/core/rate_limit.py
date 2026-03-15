from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock


@dataclass
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


class TokenBucketRateLimiter:
    def __init__(
        self,
        *,
        enabled: bool,
        rate_per_minute: int,
        burst: int,
        state_ttl_seconds: int = 10 * 60,
    ) -> None:
        self._enabled = enabled
        self._rate_per_second = max(0.0, float(rate_per_minute) / 60.0)
        self._capacity = max(1.0, float(burst))
        self._state_ttl_seconds = max(60, int(state_ttl_seconds))
        self._lock = Lock()
        # key -> (tokens, last_ts, last_seen_ts)
        self._state: dict[str, tuple[float, float, float]] = {}

    def decide(self, key: str, cost: float = 1.0) -> RateLimitDecision:
        if not self._enabled:
            return RateLimitDecision(allowed=True)
        now = time.monotonic()
        with self._lock:
            tokens, last_ts, _ = self._state.get(key, (self._capacity, now, now))
            elapsed = max(0.0, now - last_ts)
            tokens = min(self._capacity, tokens + elapsed * self._rate_per_second)

            if tokens >= cost:
                tokens -= cost
                self._state[key] = (tokens, now, now)
                self._gc_locked(now)
                return RateLimitDecision(allowed=True)

            # Estimate when a single token will be available again.
            if self._rate_per_second <= 0:
                retry_after = self._state_ttl_seconds
            else:
                retry_after = int(max(1.0, (cost - tokens) / self._rate_per_second))
            self._state[key] = (tokens, now, now)
            self._gc_locked(now)
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

    def _gc_locked(self, now: float) -> None:
        cutoff = now - float(self._state_ttl_seconds)
        if len(self._state) <= 2000:
            # Keep overhead low in the common case.
            return
        keys_to_delete = [
            key for key, (_, __, last_seen) in self._state.items() if last_seen < cutoff
        ]
        for key in keys_to_delete:
            self._state.pop(key, None)
