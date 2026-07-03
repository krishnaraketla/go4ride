"""Phase 2 API integration tests (requires Postgres + Redis)."""

from __future__ import annotations

import os
import uuid

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_json

API = "/api/v1"


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


def _register(client: TestClient) -> tuple[str, str]:
    phone = f"+1555{uuid.uuid4().int % 10_000_000:07d}"
    otp_req = client.post(f"{API}/auth/request-otp", json={"phone": phone})
    assert otp_req.status_code == 200, otp_req.text
    otp_data = api_json(otp_req)
    assert otp_data["is_new_user"] is True
    debug_otp = otp_data["debug_otp"]
    verify = client.post(
        f"{API}/auth/verify-otp",
        json={"phone": phone, "code": debug_otp, "name": "Phase2 Rider"},
    )
    assert verify.status_code == 200, verify.text
    data = api_json(verify)
    assert data["is_new_user"] is True
    return data["access_token"], data["refresh_token"]


def test_auth_refresh(client: TestClient) -> None:
    access, refresh = _register(client)
    resp = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200, resp.text
    body = api_json(resp)
    assert body["refresh_token"] != refresh
    assert "access_token" in body


def test_insights_endpoint(client: TestClient) -> None:
    access, _ = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    resp = client.get(f"{API}/insights?period=weekly", headers=headers)
    assert resp.status_code == 200, resp.text
    data = api_json(resp)
    assert data["period"] == "weekly"
    assert "trend" in data


def test_addresses_crud(client: TestClient) -> None:
    access, _ = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    create = client.post(
        f"{API}/addresses",
        headers=headers,
        json={
            "label": "Home",
            "address_line": "1 Test Street",
            "lat": "37.7749",
            "lng": "-122.4194",
            "is_default": True,
        },
    )
    assert create.status_code == 200, create.text
    addr_id = api_json(create)["id"]
    listed = client.get(f"{API}/addresses?lat=37.7749&lng=-122.4194", headers=headers)
    assert listed.status_code == 200
    assert api_json(listed)[0]["distance_m"] is not None
    assert client.delete(f"{API}/addresses/{addr_id}", headers=headers).status_code == 200


def test_settings_and_wallet(client: TestClient) -> None:
    access, _ = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    assert client.get(f"{API}/settings", headers=headers).status_code == 200
    patch = client.patch(
        f"{API}/settings", headers=headers, json={"notifications_enabled": False}
    )
    assert api_json(patch)["notifications_enabled"] is False
    assert api_json(client.get(f"{API}/wallet", headers=headers))["balance"] in ("0", "0.00")


def test_promo_and_referral(client: TestClient) -> None:
    access, _ = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    referral = client.get(f"{API}/referral", headers=headers)
    assert referral.status_code == 200
    assert len(api_json(referral)["code"]) == 6
    promo = client.post(f"{API}/promo/apply", headers=headers, json={"code": "WELCOME5"})
    assert promo.status_code == 200, promo.text
    assert api_json(promo)["credited"] == "5.00"


def test_ride_history_status_filter(client: TestClient) -> None:
    access, _ = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    history = client.get(f"{API}/rides/history?status=terminal", headers=headers)
    assert history.status_code == 200
