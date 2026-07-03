"""Driver analytics integration tests (requires Postgres + Redis)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_json

API = "/api/v1"
PICKUP = {"lat": "37.7749", "lng": "-122.4194"}
DROP = {"lat": "37.7599", "lng": "-122.4148"}
NEAR_DRIVER = {"lat": "37.7739", "lng": "-122.4184"}
SEEDED_DRIVER_PHONE = "+15555550001"


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes")


pytestmark = pytest.mark.skipif(
    not _integration_enabled(),
    reason="Set RUN_INTEGRATION_TESTS=1 with Docker Postgres/Redis and seeded DB",
)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_DRIVER_ENABLED", "false")
    monkeypatch.setenv("OTP_DEBUG", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client(mock_env: None) -> TestClient:
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


def _rider_token(client: TestClient) -> str:
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    otp_req = client.post(f"{API}/auth/request-otp", json={"phone": phone})
    debug_otp = api_json(otp_req)["debug_otp"]
    verify = client.post(
        f"{API}/auth/verify-otp",
        json={"phone": phone, "code": debug_otp, "name": "Analytics Rider"},
    )
    return api_json(verify)["access_token"]


def _driver_token(client: TestClient) -> str:
    otp_req = client.post(
        f"{API}/driver/auth/request-otp",
        json={"phone": SEEDED_DRIVER_PHONE},
    )
    debug_otp = api_json(otp_req)["debug_otp"]
    verify = client.post(
        f"{API}/driver/auth/verify-otp",
        json={"phone": SEEDED_DRIVER_PHONE, "code": debug_otp},
    )
    return api_json(verify)["access_token"]


def _go_online(client: TestClient, driver_token: str) -> None:
    resp = client.patch(
        f"{API}/driver/status",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"status": "online", "latitude": NEAR_DRIVER["lat"], "longitude": NEAR_DRIVER["lng"]},
    )
    assert resp.status_code == 200, resp.text


def _create_and_complete_ride(client: TestClient, rider_token: str, driver_token: str) -> str:
    rider_headers = {"Authorization": f"Bearer {rider_token}"}
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    quote = client.post(f"{API}/rides/quote", json={"pickup": PICKUP, "drop": DROP})
    quote_data = api_json(quote)
    ride_type = quote_data["options"][0]["ride_type_slug"]
    create = client.post(
        f"{API}/rides",
        headers=rider_headers,
        json={
            "pickup": {**PICKUP, "address": "Pickup St"},
            "drop": {**DROP, "address": "Drop Ave"},
            "ride_type_slug": ride_type,
        },
    )
    ride_id = api_json(create)["id"]

    search = client.get(
        f"{API}/driver/rides/search",
        headers=driver_headers,
        params=NEAR_DRIVER,
    )
    rides = api_json(search)["rides"]
    assert rides, "expected searchable ride"
    assert rides[0]["id"] == ride_id

    client.post(f"{API}/driver/rides/{ride_id}/accept", headers=driver_headers)
    client.post(f"{API}/driver/rides/{ride_id}/arrived", headers=driver_headers)
    status = client.get(f"{API}/rides/{ride_id}/status", headers=rider_headers)
    otp = api_json(status)["start_otp"]
    client.post(
        f"{API}/driver/rides/{ride_id}/start",
        headers=driver_headers,
        json={"otp": otp},
    )
    client.post(f"{API}/driver/rides/{ride_id}/complete", headers=driver_headers)
    return ride_id


def test_driver_dashboard_and_earnings(client: TestClient) -> None:
    rider_token = _rider_token(client)
    driver_token = _driver_token(client)
    _go_online(client, driver_token)
    ride_id = _create_and_complete_ride(client, rider_token, driver_token)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    earnings = client.get(f"{API}/driver/profile/earnings", headers=driver_headers)
    assert earnings.status_code == 200, earnings.text
    earnings_data = api_json(earnings)
    assert Decimal(str(earnings_data["today"])) > 0
    assert earnings_data["currency"]

    dashboard = client.get(f"{API}/driver/dashboard", headers=driver_headers)
    assert dashboard.status_code == 200, dashboard.text
    dash = api_json(dashboard)
    assert dash["today_trips"] >= 1
    assert Decimal(str(dash["today_earnings"])) > 0
    assert dash["online_hours_today"] >= 0

    insights = client.get(
        f"{API}/driver/insights",
        headers=driver_headers,
        params={"period": "weekly"},
    )
    assert insights.status_code == 200, insights.text
    ins = api_json(insights)
    assert ins["rides_count"] >= 1
    assert Decimal(str(ins["earnings"])) > 0
    assert len(ins["trend"]) == 7

    history = client.get(
        f"{API}/driver/rides/history",
        headers=driver_headers,
        params={"status": "completed"},
    )
    assert history.status_code == 200, history.text
    hist = api_json(history)
    assert hist["total"] >= 1
    completed = next(r for r in hist["rides"] if r["id"] == ride_id)
    assert completed["earnings"] is not None
    assert completed["status"] == "completed"

    rate = client.post(
        f"{API}/rides/{ride_id}/rate",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={"score": 5, "comment": "Great driver"},
    )
    assert rate.status_code == 200, rate.text

    history_after = client.get(
        f"{API}/driver/rides/history",
        headers=driver_headers,
        params={"status": "completed", "limit": 5},
    )
    rated = next(r for r in api_json(history_after)["rides"] if r["id"] == ride_id)
    assert rated["rider_rating"] == 5

    stats = client.get(
        f"{API}/driver/profile/stats",
        headers=driver_headers,
        params={"period": "weekly"},
    )
    assert stats.status_code == 200, stats.text
    stats_data = api_json(stats)
    assert stats_data["completed_rides"] >= 1
    assert 0 <= stats_data["acceptance_rate"] <= 1
    assert 0 <= stats_data["completion_rate"] <= 1

    driver_rate = client.post(
        f"{API}/driver/rides/{ride_id}/rate",
        headers=driver_headers,
        json={"score": 4},
    )
    assert driver_rate.status_code == 200, driver_rate.text
