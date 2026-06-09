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


async def get_cached_eta(ride_id: str) -> int | None:
    client = await get_redis()
    value = await client.get(f"ride:{ride_id}:eta")
    return int(value) if value is not None else None


async def set_cached_eta(ride_id: str, eta_min: int, ttl_sec: int) -> None:
    client = await get_redis()
    await client.set(f"ride:{ride_id}:eta", str(eta_min), ex=ttl_sec)


async def get_cached_leg_polyline(ride_id: str) -> str | None:
    client = await get_redis()
    return await client.get(f"ride:{ride_id}:leg_polyline")


async def set_cached_leg_polyline(ride_id: str, polyline: str, ttl_sec: int = 3600) -> None:
    client = await get_redis()
    await client.set(f"ride:{ride_id}:leg_polyline", polyline, ex=ttl_sec)


async def should_publish_location_update(ride_id: str, interval_sec: int) -> bool:
    """Returns True if enough time has passed since the last location WS publish."""
    client = await get_redis()
    key = f"ride:{ride_id}:loc_throttle"
    acquired = await client.set(key, "1", nx=True, ex=interval_sec)
    return acquired is not None
