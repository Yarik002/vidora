from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def rate_limit_hit(key: str, limit: int, window_sec: int) -> bool:
    """Fixed-window counter. Returns True if the request is allowed."""
    full_key = f"rl:{key}"
    # SET NX EX + INCR in one round trip: the key always gets a TTL, even if the process dies.
    async with get_redis().pipeline(transaction=True) as pipe:
        pipe.set(full_key, 0, ex=window_sec, nx=True)
        pipe.incr(full_key)
        _, count = await pipe.execute()
    return int(count) <= limit


async def first_seen(key: str, ttl_sec: int) -> bool:
    """True only for the first call within ttl (used for view de-duplication)."""
    return bool(await get_redis().set(f"seen:{key}", "1", nx=True, ex=ttl_sec))
