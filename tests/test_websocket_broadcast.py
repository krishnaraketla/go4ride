"""Unit tests for in-process WebSocket ride event delivery."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import ws as ws_module


@pytest.mark.asyncio
async def test_broadcast_ride_event_delivers_to_connected_clients() -> None:
    ride_id = "ride-test-1"
    live_ws = AsyncMock()
    dead_ws = AsyncMock()
    dead_ws.send_text.side_effect = RuntimeError("socket closed")

    ws_module._connections[ride_id] = {live_ws, dead_ws}
    try:
        payload = {"type": "status", "status": "driver_assigned"}
        await ws_module.broadcast_ride_event(ride_id, json.dumps(payload))

        live_ws.send_text.assert_awaited_once_with(json.dumps(payload))
        dead_ws.send_text.assert_awaited_once()
        assert dead_ws not in ws_module._connections[ride_id]
        assert live_ws in ws_module._connections[ride_id]
    finally:
        ws_module._connections.pop(ride_id, None)


@pytest.mark.asyncio
async def test_publish_ride_event_uses_in_process_broadcast_by_default() -> None:
    from app.core.redis import publish_ride_event

    ride_id = "ride-test-2"
    ws_client = AsyncMock()
    ws_module._connections[ride_id] = {ws_client}
    try:
        payload = {"type": "location_update", "ride_id": ride_id}
        await publish_ride_event(ride_id, payload)
        ws_client.send_text.assert_awaited_once_with(json.dumps(payload))
    finally:
        ws_module._connections.pop(ride_id, None)
