"""
Rate limiting functionality using Redis.

FAIL-CLOSED BEHAVIOR:
When Redis is unavailable or circuit breaker is open, rate limiter raises
ServiceUnavailableException (503) to prevent bypassing rate limits during outages.
"""

import os
import logging
from fastapi import Request, HTTPException, status
import redis.asyncio as redis
from pybreaker import CircuitBreaker

from core.exceptions import RateLimitException, ServiceUnavailableException

logger = logging.getLogger("cryptotrader.rate_limit")

# Use the same REDIS_URL as Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Global Redis client
_redis_client = None

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
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
            # Wrap ping in circuit breaker to detect repeated failures
            await redis_breaker.call(lambda: _redis_client.ping())
        except Exception as e:
            logger.error(
                "redis_connection_failed",
                extra={
                    "error": str(e),
                    "redis_url": REDIS_URL.split("@")[-1],  # Log without credentials
                    "circuit_state": redis_breaker.current_state,
                }
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
