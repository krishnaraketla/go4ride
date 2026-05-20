from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def publish_ride_event(ride_id: str, payload: dict[str, Any]) -> None:
    import json

    client = await get_redis()
    await client.publish(f"ride:{ride_id}", json.dumps(payload))


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Returns True if rate limit exceeded."""
    client = await get_redis()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, window_seconds)
    return count > limit


async def store_idempotency(key: str, response: str, ttl_seconds: int = 86400) -> bool:
    """Returns False if key already exists."""
    client = await get_redis()
    return await client.set(f"idempotency:{key}", response, nx=True, ex=ttl_seconds) is not None


async def get_idempotency(key: str) -> str | None:
    client = await get_redis()
    return await client.get(f"idempotency:{key}")
