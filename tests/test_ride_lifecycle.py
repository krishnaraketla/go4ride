"""Integration tests for mock ride lifecycle (requires Postgres + Redis + seed)."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_json

API = "/api/v1"
PICKUP = {"lat": "37.7749", "lng": "-122.4194"}
DROP = {"lat": "37.7599", "lng": "-122.4148"}


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes")


pytestmark = pytest.mark.skipif(
    not _integration_enabled(),
    reason="Set RUN_INTEGRATION_TESTS=1 with Docker Postgres/Redis and seeded DB",
)


@pytest.fixture
def mock_driver_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_DRIVER_ENABLED", "true")
    monkeypatch.setenv("MOCK_DRIVER_AUTO_ADVANCE", "true")
    monkeypatch.setenv("MOCK_DRIVER_ASSIGN_DELAY_SEC", "1")
    monkeypatch.setenv("MOCK_DRIVER_STEP_DELAY_SEC", "1")
    monkeypatch.setenv("OTP_DEBUG", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client(mock_driver_fast: None) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_clients() -> None:
    yield
    import asyncio

    from app.core.config import get_settings
    from app.db.session import engine

    get_settings.cache_clear()

    async def _cleanup() -> None:
        await close_redis()
        await engine.dispose()

    asyncio.run(_cleanup())


def _register_and_token(client: TestClient, phone: str) -> str:
    otp_req = client.post(f"{API}/auth/request-otp", json={"phone": phone})
    assert otp_req.status_code == 200, otp_req.text
    otp_data = api_json(otp_req)
    debug_otp = otp_data.get("debug_otp")
    assert debug_otp, "OTP_DEBUG must be true for integration tests"
    verify = client.post(
        f"{API}/auth/verify-otp",
        json={
            "phone": phone,
            "code": debug_otp,
            "name": "Lifecycle Test Rider",
        },
    )
    assert verify.status_code == 200, verify.text
    return api_json(verify)["access_token"]


def test_full_mock_lifecycle(client: TestClient) -> None:
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    token = _register_and_token(client, phone)
    headers = {"Authorization": f"Bearer {token}"}

    quote = client.post(f"{API}/rides/quote", json={"pickup": PICKUP, "drop": DROP})
    assert quote.status_code == 200, quote.text
    quote_data = api_json(quote)

    create = client.post(
        f"{API}/rides",
        headers=headers,
        json={
            "pickup": PICKUP,
            "drop": DROP,
            "pickup_address": quote_data["pickup_address"],
            "drop_address": quote_data["drop_address"],
            "ride_type_slug": "mini",
        },
    )
    assert create.status_code == 200, create.text
    created = api_json(create)
    ride_id = created["id"]
    assert created["status"] == "searching_driver"
    assert "route_polyline" in created

    statuses: list[str] = []
    with client.websocket_connect(f"/api/v1/ws/rides/{ride_id}?token={token}") as ws:
        connected = ws.receive_json()
        assert connected.get("type") == "connected"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            payload = ws.receive_json()
            if payload.get("type") == "status" and payload.get("status"):
                statuses.append(payload["status"])
            elif payload.get("status"):
                statuses.append(payload["status"])
            if payload.get("status") == "completed":
                assert payload.get("type") in (None, "status")
                break

    assert "driver_assigned" in statuses
    assert "completed" in statuses

    detail = client.get(f"{API}/rides/{ride_id}", headers=headers)
    assert detail.status_code == 200
    body = api_json(detail)
    assert body["status"] == "completed"
    assert body["driver"] is not None
    assert body["driver"]["vehicle_plate"] == "KA01AB1234"
    assert body["final_fare"] is not None

    history = client.get(f"{API}/rides/history", headers=headers, params={"limit": 5})
    assert history.status_code == 200
    items = api_json(history)["items"]
    assert any(i["id"] == ride_id and i["status"] == "completed" for i in items)


def test_cancel_after_driver_assigned(client: TestClient) -> None:
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    token = _register_and_token(client, phone)
    headers = {"Authorization": f"Bearer {token}"}

    quote = client.post(f"{API}/rides/quote", json={"pickup": PICKUP, "drop": DROP})
    assert quote.status_code == 200
    quote_data = api_json(quote)

    create = client.post(
        f"{API}/rides",
        headers=headers,
        json={
            "pickup": PICKUP,
            "drop": DROP,
            "pickup_address": quote_data["pickup_address"],
            "drop_address": quote_data["drop_address"],
            "ride_type_slug": "mini",
        },
    )
    assert create.status_code == 200
    ride_id = api_json(create)["id"]

    for _ in range(20):
        time.sleep(0.5)
        status_resp = client.get(f"{API}/rides/{ride_id}/status", headers=headers)
        if api_json(status_resp)["status"] == "driver_assigned":
            break
    else:
        pytest.fail("Ride did not reach driver_assigned in time")

    cancel = client.post(f"{API}/rides/{ride_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert api_json(cancel)["status"] == "cancelled"

    time.sleep(2.0)
    status_resp = client.get(f"{API}/rides/{ride_id}/status", headers=headers)
    assert api_json(status_resp)["status"] == "cancelled"
