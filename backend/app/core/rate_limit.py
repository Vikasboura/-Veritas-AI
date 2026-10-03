"""
app/core/rate_limit.py
───────────────────────
Sliding-window rate limiter backed by Redis.
Uses a sorted-set per user to track request timestamps.
"""
from __future__ import annotations

import time
from uuid import UUID

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
log = get_logger(__name__)

# Lua script for atomic sliding-window check
# Returns 1 if request is allowed, 0 if rate-limited
_LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cutoff = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, now .. math.random())
    redis.call('EXPIRE', key, window + 1)
    return 1
end
return 0
"""


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._script = redis_client.register_script(_LUA_SCRIPT)

    async def is_allowed(self, user_id: str | UUID) -> bool:
        """
        Returns True if the request is within the rate limit.
        Returns False if the user has exceeded their quota.
        """
        key = f"rl:{user_id}"
        now_ms = int(time.time() * 1000)
        window_ms = settings.RATE_LIMIT_WINDOW_SECONDS * 1000
        limit = settings.RATE_LIMIT_REQUESTS

        try:
            result = await self._script(
                keys=[key],
                args=[now_ms, window_ms, limit],
            )
            return bool(result)
        except Exception:
            log.warning("rate_limiter_error", user_id=str(user_id))
            # Fail open: allow request if Redis is unreachable
            return True
