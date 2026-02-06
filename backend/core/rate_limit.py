"""
Rate limiting functionality using Redis.

FAIL-CLOSED BEHAVIOR:
When Redis is unavailable or circuit breaker is open, rate limiter raises
ServiceUnavailableException (503) to prevent bypassing rate limits during outages.
"""

import logging
import os
import time
import asyncio
from typing import Dict, Tuple

from fastapi import Request, HTTPException, status
import redis.asyncio as redis
from redis.exceptions import WatchError
from pybreaker import CircuitBreaker
from sqlalchemy import select

from core.exceptions import RateLimitException, ServiceUnavailableException
from db.database import AsyncSessionLocal
from db.models import RiskSettings

logger = logging.getLogger("cryptotrader.rate_limit")

# Use the same REDIS_URL as Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
ALLOW_FAKE_REDIS = (
    os.getenv(
        "RATE_LIMITER_FAKE_REDIS",
        "false" if ENVIRONMENT == "production" else "true",
    ).lower()
    == "true"
)
BYPASS_RATE_LIMIT_ON_FAKE = (
    os.getenv("RATE_LIMITER_BYPASS_ON_FAKE", "true").lower() == "true"
)

# Global Redis client
_redis_client = None
_using_fake_redis = False

# Circuit breaker for Redis connection
# Opens after 5 consecutive failures, stays open for 60 seconds before retry
redis_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="redis_rate_limiter"
)

async def get_redis():
    """
    Get or create the global Redis client.

    FAIL-CLOSED: Returns None when Redis is unreachable, allowing callers
    to raise ServiceUnavailableException instead of failing open.

    Raises:
        Exception: Propagated from circuit breaker when open
    """
    global _redis_client, _using_fake_redis
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
            # Wrap ping in circuit breaker to detect repeated failures
            await redis_breaker.call(lambda: _redis_client.ping())
            _using_fake_redis = False
        except Exception as e:
            logger.error(
                "redis_connection_failed",
                extra={
                    "error": str(e),
                    "redis_url": REDIS_URL.split("@")[-1],  # Log without credentials
                    "circuit_state": redis_breaker.current_state,
                }
            )
            if ALLOW_FAKE_REDIS:
                try:
                    from fakeredis.aioredis import FakeRedis  # type: ignore

                    _redis_client = FakeRedis()
                    _using_fake_redis = True
                    logger.warning(
                        "redis_fallback_fake",
                        extra={
                            "redis_url": REDIS_URL.split("@")[-1],
                            "environment": ENVIRONMENT,
                        },
                    )
                    return _redis_client
                except Exception as fake_err:
                    logger.error(
                        "redis_fallback_fake_failed",
                        extra={
                            "error": str(fake_err),
                            "redis_url": REDIS_URL.split("@")[-1],
                        },
                    )
            # FAIL-CLOSED: Return None to trigger ServiceUnavailableException
            return None
    return _redis_client

async def check_rate_limit(key: str, limit: int, window: int) -> None:
    """
    Check if action exceeds limit within window seconds.

    FAIL-CLOSED: Raises structured exceptions when Redis is unavailable
    or rate limit exceeded. Never returns True/False to prevent fail-open behavior.

    Args:
        key: The unique key to rate limit (e.g. 'ip:1.2.3.4')
        limit: Max number of requests allowed
        window: Time window in seconds

    Raises:
        RateLimitException: When rate limit exceeded (429 + Retry-After)
        ServiceUnavailableException: When Redis unavailable (503 + Retry-After)
    """
    r = await get_redis()
    if _using_fake_redis and BYPASS_RATE_LIMIT_ON_FAKE:
        return True
    if not r:
        # FAIL-CLOSED: Redis unavailable, deny all requests
        logger.warning(
            "rate_limit_unavailable",
            extra={
                "key": key,
                "limit": limit,
                "window": window,
                "circuit_state": redis_breaker.current_state,
            }
        )
        raise ServiceUnavailableException(
            service="rate_limiter",
            retry_after=60,
            details={"reason": "Redis connection unavailable or circuit breaker open"}
        )

    try:
        # Use a pipeline to ensure atomicity of incr + expire (mostly)
        # Note: incr is atomic. expire is separate.
        # For strict correctness we might use Lua script, but this is sufficient.
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window)

        if current > limit:
            logger.info(
                "rate_limit_exceeded",
                extra={
                    "key": key,
                    "current": current,
                    "limit": limit,
                    "window": window,
                }
            )
            raise RateLimitException(
                retry_after=window,
                details={"current": current, "limit": limit, "window": window}
            )

        # Request allowed, return normally (no exception)
        logger.debug(
            "rate_limit_passed",
            extra={"key": key, "current": current, "limit": limit}
        )
        return True

    except RateLimitException:
        # Re-raise typed exceptions
        raise
    except Exception as e:
        # FAIL-CLOSED: Redis errors deny requests
        logger.error(
            "rate_limit_check_failed",
            extra={
                "key": key,
                "error": str(e),
                "error_type": e.__class__.__name__,
            },
            exc_info=True
        )
        raise ServiceUnavailableException(
            service="rate_limiter",
            retry_after=60,
            details={"reason": f"Redis error: {e.__class__.__name__}"}
        )
    return True

class RateLimiter:
    """
    FastAPI dependency for IP-based rate limiting.

    FAIL-CLOSED: Raises RateLimitException or ServiceUnavailableException
    when limits exceeded or Redis unavailable.
    """
    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds

    async def __call__(self, request: Request):
        if not request.client:
            # Should not happen in standard HTTP, but handle gracefully
            logger.warning("rate_limit_no_client", extra={"path": request.url.path})
            return

        client_ip = request.client.host
        # Key includes path to scope limit to specific endpoint
        key = f"rate_limit:{request.url.path}:{client_ip}"

        # check_rate_limit now raises exceptions instead of returning bool
        await check_rate_limit(key, self.times, self.seconds)


class KrakenRateLimitTimeout(Exception):
    """Raised when Kraken rate limiter cannot acquire capacity before timeout."""


class KrakenRateLimiter:
    """Redis-backed Kraken call counter with tier-aware decay."""

    _COUNTER_KEY = "rate_limit:kraken:counter"
    _TIER_CACHE_TTL_SECONDS = 30.0
    _DEFAULT_ACQUIRE_TIMEOUT_SECONDS = 10.0
    _DEFAULT_POLL_SECONDS = 0.05
    _MAX_POLL_SECONDS = 0.5
    _tier_cache: Tuple[str, float] = ("starter", 0.0)

    _TIER_LIMITS: Dict[str, Dict[str, float]] = {
        "starter": {"limit": 15.0, "decay_per_second": 0.5},
        "intermediate": {"limit": 20.0, "decay_per_second": 1.0},
        "pro": {"limit": 20.0, "decay_per_second": 2.0},
    }

    @classmethod
    async def _consume_budget(
        cls,
        redis_client,
        now: float,
        weight: float,
        limit: float,
        decay_per_second: float,
        ttl_seconds: int,
    ) -> Tuple[int, float, float]:
        while True:
            async with redis_client.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(cls._COUNTER_KEY)
                    state = await pipe.hgetall(cls._COUNTER_KEY)

                    counter = float(state.get("counter", 0.0))
                    updated_at = float(state.get("updated_at", now))
                    elapsed = max(0.0, now - updated_at)
                    decayed = max(0.0, counter - (elapsed * decay_per_second))

                    pipe.multi()
                    pipe.hset(
                        cls._COUNTER_KEY,
                        mapping={"counter": decayed, "updated_at": now},
                    )
                    pipe.expire(cls._COUNTER_KEY, ttl_seconds)

                    if (decayed + weight) <= limit:
                        new_counter = decayed + weight
                        pipe.hset(
                            cls._COUNTER_KEY,
                            mapping={"counter": new_counter, "updated_at": now},
                        )
                        await pipe.execute()
                        return 1, new_counter, 0.0

                    await pipe.execute()
                    wait_seconds = max(0.0, (decayed + weight - limit) / decay_per_second)
                    return 0, decayed, wait_seconds
                except WatchError:
                    continue

    @classmethod
    async def _load_kraken_tier(cls) -> str:
        now = time.monotonic()
        cached_tier, cached_until = cls._tier_cache
        if now < cached_until:
            return cached_tier

        tier = "starter"
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(RiskSettings.kraken_tier).order_by(RiskSettings.updated_at.desc()).limit(1)
                )
                db_tier = result.scalar_one_or_none()
                if isinstance(db_tier, str) and db_tier.strip():
                    tier = db_tier.strip().lower()
        except Exception:
            logger.warning("kraken_rate_limiter_settings_lookup_failed", exc_info=True)

        if tier not in cls._TIER_LIMITS:
            tier = "starter"

        cls._tier_cache = (tier, now + cls._TIER_CACHE_TTL_SECONDS)
        return tier

    @classmethod
    async def acquire(
        cls,
        weight: float = 1.0,
        timeout_seconds: float = _DEFAULT_ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        """Wait asynchronously until the Kraken budget can accept this request."""
        if weight <= 0:
            return

        redis_client = await get_redis()
        if not redis_client:
            raise ServiceUnavailableException(
                service="kraken_rate_limiter",
                retry_after=60,
                details={"reason": "Redis unavailable for Kraken limiter"},
            )

        tier = await cls._load_kraken_tier()
        config = cls._TIER_LIMITS[tier]
        limit = float(config["limit"])
        decay_per_second = float(config["decay_per_second"])
        if decay_per_second <= 0:
            decay_per_second = 0.1

        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        ttl_seconds = max(1, int((limit / decay_per_second) + 5))

        while True:
            now = time.monotonic()
            try:
                allowed, counter, wait_seconds = await cls._consume_budget(
                    redis_client,
                    now,
                    float(weight),
                    limit,
                    decay_per_second,
                    ttl_seconds,
                )
            except Exception as exc:
                raise ServiceUnavailableException(
                    service="kraken_rate_limiter",
                    retry_after=60,
                    details={"reason": f"Redis error: {exc.__class__.__name__}"},
                ) from exc

            if int(allowed) == 1:
                logger.debug(
                    "kraken_rate_limiter_acquired",
                    extra={"tier": tier, "weight": weight, "counter": float(counter)},
                )
                return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise KrakenRateLimitTimeout(
                    f"Unable to acquire Kraken rate-limit budget within {timeout_seconds:.2f}s"
                )

            sleep_for = min(max(float(wait_seconds), cls._DEFAULT_POLL_SECONDS), cls._MAX_POLL_SECONDS, remaining)
            await asyncio.sleep(sleep_for)
