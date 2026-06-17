import asyncio
import logging
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.config import get_settings
from app.core.redis import get_pubsub_redis, reset_pubsub_redis
from app.core.security import verify_token
from app.db.session import async_session_factory
from app.services import ride_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_connections: dict[str, set[WebSocket]] = {}
_listener_tasks: dict[str, asyncio.Task] = {}


async def broadcast_ride_event(ride_id: str, data: str) -> None:
    """Deliver a ride event to all WebSocket clients on this process."""
    dead: set[WebSocket] = set()
    for ws in list(_connections.get(ride_id, set())):
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _connections.get(ride_id, set()).discard(ws)


def _channel(ride_id: str) -> str:
    return f"ride:{ride_id}"


async def _redis_listener(ride_id: str) -> None:
    channel = _channel(ride_id)
    try:
        while _connections.get(ride_id):
            pubsub = None
            try:
                client = await get_pubsub_redis()
                pubsub = client.pubsub()
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if not _connections.get(ride_id):
                        break
                    if message["type"] != "message":
                        continue
                    data = message["data"]
                    text = data if isinstance(data, str) else data.decode()
                    await broadcast_ride_event(ride_id, text)
            except asyncio.CancelledError:
                raise
            except (redis.TimeoutError, redis.ConnectionError) as exc:
                if not _connections.get(ride_id):
                    break
                logger.warning(
                    "websocket_pubsub_reconnecting",
                    extra={"ride_id": ride_id, "error": str(exc)},
                )
                await reset_pubsub_redis()
                await asyncio.sleep(1)
            except redis.RedisError:
                if not _connections.get(ride_id):
                    break
                logger.exception(
                    "websocket_pubsub_listener_failed",
                    extra={"ride_id": ride_id},
                )
                await reset_pubsub_redis()
                await asyncio.sleep(1)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.unsubscribe(channel)
                    except redis.RedisError:
                        pass
                    try:
                        await pubsub.close()
                    except redis.RedisError:
                        pass
    except asyncio.CancelledError:
        pass
    finally:
        _listener_tasks.pop(ride_id, None)


def _ensure_redis_listener(ride_id: str) -> None:
    task = _listener_tasks.get(ride_id)
    if task is not None and not task.done():
        return
    _listener_tasks[ride_id] = asyncio.create_task(_redis_listener(ride_id))


def _stop_redis_listener(ride_id: str) -> None:
    task = _listener_tasks.pop(ride_id, None)
    if task is not None and not task.done():
        task.cancel()


def _on_client_disconnect(ride_id: str) -> None:
    if _connections.get(ride_id):
        return
    _connections.pop(ride_id, None)
    if get_settings().websocket_redis_fanout:
        _stop_redis_listener(ride_id)


async def shutdown_websocket_listeners() -> None:
    for ride_id in list(_listener_tasks):
        _stop_redis_listener(ride_id)
    if _listener_tasks:
        await asyncio.gather(*_listener_tasks.values(), return_exceptions=True)
        _listener_tasks.clear()


@router.websocket("/ws/rides/{ride_id}")
async def ride_websocket(
    websocket: WebSocket,
    ride_id: UUID,
    token: str = Query(...),
):
    try:
        payload = verify_token(token, "access")
        user_id = payload["sub"]
    except (JWTError, ValueError):
        logger.warning("websocket_auth_failed", extra={"ride_id": str(ride_id), "code": 4001})
        await websocket.close(code=4001)
        return

    async with async_session_factory() as db:
        if not await ride_service.user_can_access_ride_ws(db, UUID(user_id), ride_id):
            logger.warning(
                "websocket_forbidden",
                extra={"ride_id": str(ride_id), "user_id": user_id, "code": 4003},
            )
            await websocket.close(code=4003)
            return

    await websocket.accept()
    key = str(ride_id)
    _connections.setdefault(key, set()).add(websocket)
    if get_settings().websocket_redis_fanout:
        _ensure_redis_listener(key)

    await websocket.send_json(
        {"type": "connected", "ride_id": key, "user_id": user_id}
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connections.get(key, set()).discard(websocket)
        _on_client_disconnect(key)
