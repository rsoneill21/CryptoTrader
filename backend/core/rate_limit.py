"""
Rate limiting functionality using Redis.
"""

import os
import logging
from fastapi import Request, HTTPException, status
import redis.asyncio as redis

logger = logging.getLogger("cryptotrader.rate_limit")

# Use the same REDIS_URL as Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Global Redis client
_redis_client = None

async def get_redis():
    """Get or create the global Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
            await _redis_client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            # If we can't connect, we might want to return None or raise
            # For now, return None and let callers handle fallback (fail open)
            return None
    return _redis_client

async def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """
    Check if action exceeds limit within window seconds.
    
    Args:
        key: The unique key to rate limit (e.g. 'ip:1.2.3.4')
        limit: Max number of requests allowed
        window: Time window in seconds
        
    Returns:
        True if request is allowed, False if limit exceeded.
    """
    r = await get_redis()
    if not r:
        # Fail open if Redis is unavailable
        return True
        
    try:
        # Use a pipeline to ensure atomicity of incr + expire (mostly)
        # Note: incr is atomic. expire is separate. 
        # For strict correctness we might use Lua script, but this is sufficient.
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, window)
            
        if current > limit:
            return False
            
        return True
    except Exception as e:
        logger.error(f"Redis error checking rate limit for {key}: {e}")
        # Fail open
        return True

class RateLimiter:
    """
    FastAPI dependency for IP-based rate limiting.
    """
    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds

    async def __call__(self, request: Request):
        if not request.client:
            return # Should not happen in standard HTTP
            
        client_ip = request.client.host
        # Key includes path to scope limit to specific endpoint
        key = f"rate_limit:{request.url.path}:{client_ip}"
        
        allowed = await check_rate_limit(key, self.times, self.seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later."
            )
