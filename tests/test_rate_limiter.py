from __future__ import annotations

import asyncio
import importlib
import sys

import pytest

from rate_limiter import TokenBucket


def test_acquire_is_immediate_when_tokens_available():
    bucket = TokenBucket(rate=2.0, capacity=2.0, clock=lambda: 100.0)

    async def run():
        await bucket.acquire()
        await bucket.acquire()

    asyncio.run(run())
    assert bucket._tokens == pytest.approx(0.0)


def test_acquire_waits_for_refill_when_empty(monkeypatch):
    now = [0.0]

    def clock():
        return now[0]

    async def fake_sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    bucket = TokenBucket(rate=1.0, capacity=1.0, clock=clock)

    async def run():
        await bucket.acquire()  # consumes the only token, no wait
        await bucket.acquire()  # bucket empty, must wait ~1s to refill one

    asyncio.run(run())
    assert now[0] == pytest.approx(1.0, rel=0.05)


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        TokenBucket(rate=0)
    with pytest.raises(ValueError):
        TokenBucket(rate=-1.0)


def _reload_rate_limiter_module():
    if "rate_limiter" in sys.modules:
        del sys.modules["rate_limiter"]
    return importlib.import_module("rate_limiter")


def test_default_rate_from_env(monkeypatch):
    monkeypatch.delenv("VEX_MAX_REQUESTS_PER_SEC", raising=False)
    module = _reload_rate_limiter_module()
    assert module._LIMITER._rate == module.DEFAULT_MAX_REQUESTS_PER_SEC


def test_rate_configurable_from_env(monkeypatch):
    monkeypatch.setenv("VEX_MAX_REQUESTS_PER_SEC", "7.5")
    module = _reload_rate_limiter_module()
    assert module._LIMITER._rate == pytest.approx(7.5)


def test_singleton_has_no_burst_allowance(monkeypatch):
    # A large fan-out of concurrent callers (e.g. fetching hundreds of
    # missing team profiles at once) must not be able to drain banked
    # credit in a near-instant cluster — observed live to trip VEX's 429s
    # even though the trailing average rate stayed within budget. Capacity
    # must stay pinned to 1 regardless of the configured rate.
    monkeypatch.setenv("VEX_MAX_REQUESTS_PER_SEC", "7.5")
    module = _reload_rate_limiter_module()
    assert module._LIMITER._capacity == pytest.approx(1.0)


def test_non_positive_rate_from_env_raises(monkeypatch):
    monkeypatch.setenv("VEX_MAX_REQUESTS_PER_SEC", "0")
    with pytest.raises(RuntimeError, match="VEX_MAX_REQUESTS_PER_SEC"):
        _reload_rate_limiter_module()
