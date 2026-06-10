import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.redis import get_redis
from app.core.security import verify_token
from app.db.session import async_session_factory
from app.services import ride_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_connections: dict[str, set[WebSocket]] = {}
_redis_listeners: set[str] = set()


async def _subscribe_redis(ride_id: str) -> None:
    if ride_id in _redis_listeners:
        return
    _redis_listeners.add(ride_id)
    client = await get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(f"ride:{ride_id}")

    async def listener():
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = message["data"]
                dead = set()
                for ws in _connections.get(ride_id, set()):
                    try:
                        await ws.send_text(data if isinstance(data, str) else data.decode())
                    except Exception:
                        dead.add(ws)
                for ws in dead:
                    _connections.get(ride_id, set()).discard(ws)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("websocket_pubsub_listener_failed", extra={"ride_id": ride_id})
        finally:
            _redis_listeners.discard(ride_id)
            await pubsub.unsubscribe(f"ride:{ride_id}")
            await pubsub.close()

    asyncio.create_task(listener())


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
        if not await ride_service.rider_owns_ride(db, UUID(user_id), ride_id):
            logger.warning(
                "websocket_forbidden",
                extra={"ride_id": str(ride_id), "user_id": user_id, "code": 4003},
            )
            await websocket.close(code=4003)
            return

    await websocket.accept()
    key = str(ride_id)
    _connections.setdefault(key, set()).add(websocket)
    await _subscribe_redis(key)

    await websocket.send_json(
        {"type": "connected", "ride_id": key, "user_id": user_id}
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connections.get(key, set()).discard(websocket)
        if not _connections.get(key):
            _connections.pop(key, None)
