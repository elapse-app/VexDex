from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from os import getenv

logger = logging.getLogger(__name__)

DEFAULT_MAX_REQUESTS_PER_SEC = 3.0


class TokenBucket:
    """Paces callers to at most `rate` acquisitions/sec, with a small burst
    allowance. Proactive pacing (vs. reacting to 429s after the fact) is what
    actually keeps a fan-out of many concurrent requests under a time-window
    rate limit — a concurrency cap alone doesn't, since fast-completing
    requests can still be dispatched at an unbounded rate."""

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._capacity = capacity if capacity is not None else max(1.0, rate)
        self._clock = clock
        self._tokens = self._capacity
        self._last_refill = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                elapsed = now - self._last_refill
                self._last_refill = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

                if self._tokens >= 1:
                    self._tokens -= 1
                    return

                wait = (1 - self._tokens) / self._rate
                logger.debug("Rate limiter: no tokens available, waiting %.2fs", wait)
                await asyncio.sleep(wait)


def _load_rate_from_env() -> float:
    raw = getenv("VEX_MAX_REQUESTS_PER_SEC")
    if not raw:
        return DEFAULT_MAX_REQUESTS_PER_SEC
    rate = float(raw)
    if rate <= 0:
        raise RuntimeError("VEX_MAX_REQUESTS_PER_SEC must be a positive number.")
    return rate


_LIMITER = TokenBucket(rate=_load_rate_from_env())


async def acquire() -> None:
    await _LIMITER.acquire()
