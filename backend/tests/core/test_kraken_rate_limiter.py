import asyncio
import time

import pytest
from fakeredis.aioredis import FakeRedis

from core.exceptions import ServiceUnavailableException
from core.rate_limit import KrakenRateLimiter, KrakenRateLimitTimeout


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis(decode_responses=True)

    async def _fake_get_redis():
        return client

    async def _fake_tier():
        return "starter"

    monkeypatch.setattr("core.rate_limit.get_redis", _fake_get_redis)
    monkeypatch.setattr(KrakenRateLimiter, "_load_kraken_tier", _fake_tier)
    return client


@pytest.mark.asyncio
async def test_kraken_rate_limiter_applies_decay_and_waits(fake_redis, monkeypatch):
    monkeypatch.setattr(
        KrakenRateLimiter,
        "_TIER_LIMITS",
        {"starter": {"limit": 2.0, "decay_per_second": 1.0}},
    )

    await KrakenRateLimiter.acquire(weight=2.0, timeout_seconds=0.2)

    started = time.monotonic()
    await KrakenRateLimiter.acquire(weight=1.0, timeout_seconds=2.0)
    elapsed = time.monotonic() - started

    assert elapsed >= 0.8


@pytest.mark.asyncio
async def test_kraken_rate_limiter_handles_concurrency(fake_redis, monkeypatch):
    monkeypatch.setattr(
        KrakenRateLimiter,
        "_TIER_LIMITS",
        {"starter": {"limit": 2.0, "decay_per_second": 10.0}},
    )

    durations = []

    async def _acquire_once():
        started = time.monotonic()
        await KrakenRateLimiter.acquire(weight=1.0, timeout_seconds=1.0)
        durations.append(time.monotonic() - started)

    await asyncio.gather(_acquire_once(), _acquire_once(), _acquire_once())

    assert len(durations) == 3
    assert max(durations) >= 0.09


@pytest.mark.asyncio
async def test_kraken_rate_limiter_times_out_when_capacity_not_available(fake_redis, monkeypatch):
    monkeypatch.setattr(
        KrakenRateLimiter,
        "_TIER_LIMITS",
        {"starter": {"limit": 1.0, "decay_per_second": 0.1}},
    )

    await KrakenRateLimiter.acquire(weight=1.0, timeout_seconds=0.2)

    with pytest.raises(KrakenRateLimitTimeout):
        await KrakenRateLimiter.acquire(weight=1.0, timeout_seconds=0.1)


@pytest.mark.asyncio
async def test_kraken_rate_limiter_fails_closed_without_redis(monkeypatch):
    async def _none_get_redis():
        return None

    monkeypatch.setattr("core.rate_limit.get_redis", _none_get_redis)

    with pytest.raises(ServiceUnavailableException):
        await KrakenRateLimiter.acquire(weight=1.0)
