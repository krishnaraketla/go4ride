import logging
from collections.abc import Awaitable
from typing import Any, TypeVar

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_pubsub_redis: redis.Redis | None = None

T = TypeVar("T")


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def get_pubsub_redis() -> redis.Redis:
    """Dedicated Redis client for long-lived pub/sub reads (no socket timeout)."""
    global _pubsub_redis
    if _pubsub_redis is None:
        settings = get_settings()
        _pubsub_redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=None,
        )
    return _pubsub_redis


async def reset_pubsub_redis() -> None:
    global _pubsub_redis
    if _pubsub_redis is not None:
        try:
            await _pubsub_redis.aclose()
        except redis.RedisError:
            pass
        _pubsub_redis = None


async def close_redis() -> None:
    global _redis, _pubsub_redis
    if _pubsub_redis is not None:
        try:
            await _pubsub_redis.aclose()
        except redis.RedisError:
            pass
        _pubsub_redis = None
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("redis_connection_closed")


async def _redis_call(operation: str, coro: Awaitable[T]) -> T:
    try:
        return await coro
    except redis.RedisError:
        logger.exception("redis_operation_failed", extra={"operation": operation})
        raise


async def check_redis() -> bool:
    try:
        client = await get_redis()
        await client.ping()
        return True
    except redis.RedisError:
        logger.exception("redis_check_failed")
        return False


async def publish_ride_event(ride_id: str, payload: dict[str, Any]) -> None:
    import json

    from app.api.v1.ws import broadcast_ride_event

    data = json.dumps(payload)
    settings = get_settings()
    if settings.websocket_redis_fanout:
        client = await get_redis()
        await _redis_call(
            "publish_ride_event",
            client.publish(f"ride:{ride_id}", data),
        )
    else:
        await broadcast_ride_event(ride_id, data)


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Returns True if rate limit exceeded."""
    client = await get_redis()

    async def _check() -> bool:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        return count > limit

    return await _redis_call("check_rate_limit", _check())


async def store_idempotency(key: str, response: str, ttl_seconds: int = 86400) -> bool:
    """Returns False if key already exists."""
    client = await get_redis()
    result = await _redis_call(
        "store_idempotency",
        client.set(f"idempotency:{key}", response, nx=True, ex=ttl_seconds),
    )
    return result is not None


async def get_idempotency(key: str) -> str | None:
    client = await get_redis()
    return await _redis_call("get_idempotency", client.get(f"idempotency:{key}"))


async def get_cached_eta(ride_id: str) -> int | None:
    client = await get_redis()
    value = await _redis_call("get_cached_eta", client.get(f"ride:{ride_id}:eta"))
    return int(value) if value is not None else None


async def set_cached_eta(ride_id: str, eta_min: int, ttl_sec: int) -> None:
    client = await get_redis()
    await _redis_call(
        "set_cached_eta",
        client.set(f"ride:{ride_id}:eta", str(eta_min), ex=ttl_sec),
    )


async def get_cached_leg_polyline(ride_id: str) -> str | None:
    client = await get_redis()
    return await _redis_call(
        "get_cached_leg_polyline",
        client.get(f"ride:{ride_id}:leg_polyline"),
    )


async def set_cached_leg_polyline(ride_id: str, polyline: str, ttl_sec: int = 3600) -> None:
    client = await get_redis()
    await _redis_call(
        "set_cached_leg_polyline",
        client.set(f"ride:{ride_id}:leg_polyline", polyline, ex=ttl_sec),
    )


async def should_publish_location_update(ride_id: str, interval_sec: int) -> bool:
    """Returns True if enough time has passed since the last location WS publish."""
    client = await get_redis()

    async def _should_publish() -> bool:
        key = f"ride:{ride_id}:loc_throttle"
        acquired = await client.set(key, "1", nx=True, ex=interval_sec)
        return acquired is not None

    return await _redis_call("should_publish_location_update", _should_publish())
