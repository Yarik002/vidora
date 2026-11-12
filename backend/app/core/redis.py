from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def rate_limit_hit(key: str, limit: int, window_sec: int) -> bool:
    """Fixed-window counter. Returns True if the request is allowed."""
    redis = get_redis()
    full_key = f"rl:{key}"
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_sec)
    return count <= limit


async def first_seen(key: str, ttl_sec: int) -> bool:
    """True only for the first call within ttl (used for view de-duplication)."""
    return bool(await get_redis().set(f"seen:{key}", "1", nx=True, ex=ttl_sec))
