"""Integration tests for mock ride lifecycle (requires Postgres + Redis + seed)."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app

API = "/api/v1"
PICKUP = {"lat": "12.9716", "lng": "77.5946"}
DROP = {"lat": "12.9352", "lng": "77.6245"}


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
    debug_otp = otp_req.json().get("debug_otp")
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
    return verify.json()["access_token"]


def test_full_mock_lifecycle(client: TestClient) -> None:
    phone = f"+9198{uuid.uuid4().int % 100_000_000:08d}"
    token = _register_and_token(client, phone)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        f"{API}/rides",
        headers=headers,
        json={
            "pickup": PICKUP,
            "drop": DROP,
            "pickup_address": "Test Pickup",
            "drop_address": "Test Drop",
            "ride_type_slug": "mini",
        },
    )
    assert create.status_code == 200, create.text
    ride_id = create.json()["id"]
    assert create.json()["status"] == "searching_driver"

    statuses: list[str] = []
    with client.websocket_connect(f"/api/v1/ws/rides/{ride_id}?token={token}") as ws:
        connected = ws.receive_json()
        assert connected.get("type") == "connected"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            payload = ws.receive_json()
            if payload.get("status"):
                statuses.append(payload["status"])
            if payload.get("status") == "completed":
                break

    assert "driver_assigned" in statuses
    assert "completed" in statuses

    detail = client.get(f"{API}/rides/{ride_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "completed"
    assert body["driver"] is not None
    assert body["driver"]["vehicle_plate"] == "KA01AB1234"
    assert body["final_fare"] is not None

    history = client.get(f"{API}/rides/history", headers=headers, params={"limit": 5})
    assert history.status_code == 200
    items = history.json()["items"]
    assert any(i["id"] == ride_id and i["status"] == "completed" for i in items)


def test_cancel_after_driver_assigned(client: TestClient) -> None:
    phone = f"+9198{uuid.uuid4().int % 100_000_000:08d}"
    token = _register_and_token(client, phone)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        f"{API}/rides",
        headers=headers,
        json={
            "pickup": PICKUP,
            "drop": DROP,
            "pickup_address": "Test Pickup",
            "drop_address": "Test Drop",
            "ride_type_slug": "mini",
        },
    )
    assert create.status_code == 200
    ride_id = create.json()["id"]

    for _ in range(20):
        time.sleep(0.5)
        status_resp = client.get(f"{API}/rides/{ride_id}/status", headers=headers)
        if status_resp.json()["status"] == "driver_assigned":
            break
    else:
        pytest.fail("Ride did not reach driver_assigned in time")

    cancel = client.post(f"{API}/rides/{ride_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    time.sleep(2.0)
    status_resp = client.get(f"{API}/rides/{ride_id}/status", headers=headers)
    assert status_resp.json()["status"] == "cancelled"
