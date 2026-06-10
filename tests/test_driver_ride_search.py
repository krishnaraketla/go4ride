"""Driver ride search integration tests (requires Postgres + Redis + seed)."""

from __future__ import annotations

import os
import uuid

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_json

API = "/api/v1"
PICKUP = {"lat": "12.9716", "lng": "77.5946"}
DROP = {"lat": "12.9352", "lng": "77.6245"}
NEAR_DRIVER = {"lat": "12.9700", "lng": "77.5900"}
FAR_DRIVER = {"lat": "13.0500", "lng": "77.7000"}
SEEDED_DRIVER_PHONE = "+919999000001"


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
    phone = f"+9198{uuid.uuid4().int % 100_000_000:08d}"
    otp_req = client.post(f"{API}/auth/request-otp", json={"phone": phone})
    assert otp_req.status_code == 200, otp_req.text
    debug_otp = api_json(otp_req)["debug_otp"]
    verify = client.post(
        f"{API}/auth/verify-otp",
        json={"phone": phone, "code": debug_otp, "name": "Search Test Rider"},
    )
    assert verify.status_code == 200, verify.text
    return api_json(verify)["access_token"]


def _driver_token(client: TestClient) -> str:
    otp_req = client.post(
        f"{API}/driver/auth/request-otp",
        json={"phone": SEEDED_DRIVER_PHONE},
    )
    assert otp_req.status_code == 200, otp_req.text
    debug_otp = api_json(otp_req)["debug_otp"]
    verify = client.post(
        f"{API}/driver/auth/verify-otp",
        json={"phone": SEEDED_DRIVER_PHONE, "code": debug_otp},
    )
    assert verify.status_code == 200, verify.text
    return api_json(verify)["access_token"]


def _create_searching_ride(client: TestClient, rider_token: str) -> str:
    headers = {"Authorization": f"Bearer {rider_token}"}
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
    assert created["status"] == "searching_driver"
    return created["id"]


def test_driver_search_finds_nearby_ride(client: TestClient) -> None:
    rider_token = _rider_token(client)
    ride_id = _create_searching_ride(client, rider_token)

    driver_token = _driver_token(client)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    go_online = client.patch(
        f"{API}/driver/status",
        headers=driver_headers,
        json={
            "status": "online",
            "latitude": NEAR_DRIVER["lat"],
            "longitude": NEAR_DRIVER["lng"],
        },
    )
    assert go_online.status_code == 200, go_online.text

    search = client.get(
        f"{API}/driver/rides/search",
        headers=driver_headers,
        params={**NEAR_DRIVER, "radius_km": 5},
    )
    assert search.status_code == 200, search.text
    body = api_json(search)
    assert body["search"]["total"] >= 1
    assert any(r["id"] == ride_id for r in body["rides"])
    assert body["rides"][0]["pickup_distance_m"] >= 0


def test_driver_search_empty_when_far(client: TestClient) -> None:
    rider_token = _rider_token(client)
    _create_searching_ride(client, rider_token)

    driver_token = _driver_token(client)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    go_online = client.patch(
        f"{API}/driver/status",
        headers=driver_headers,
        json={
            "status": "online",
            "latitude": FAR_DRIVER["lat"],
            "longitude": FAR_DRIVER["lng"],
        },
    )
    assert go_online.status_code == 200, go_online.text

    search = client.get(
        f"{API}/driver/rides/search",
        headers=driver_headers,
        params={**FAR_DRIVER, "radius_km": 3},
    )
    assert search.status_code == 200, search.text
    assert api_json(search)["search"]["total"] == 0


def test_driver_search_requires_online(client: TestClient) -> None:
    driver_token = _driver_token(client)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    search = client.get(
        f"{API}/driver/rides/search",
        headers=driver_headers,
        params={**NEAR_DRIVER, "radius_km": 5},
    )
    assert search.status_code == 400, search.text
