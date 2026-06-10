"""Admin driver KYC review integration tests (requires Postgres + Redis)."""

from __future__ import annotations

import os
import uuid

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_error, api_json

API = "/api/v1"
ADMIN_KEY = "test-admin-key-secret"


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
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
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


def _register_driver(client: TestClient) -> tuple[str, str]:
    phone = f"+919876{uuid.uuid4().int % 100000:05d}"
    otp_req = client.post(
        f"{API}/driver/auth/request-otp",
        json={"phone": phone},
    )
    assert otp_req.status_code == 200, otp_req.text
    debug_otp = api_json(otp_req)["debug_otp"]

    verify = client.post(
        f"{API}/driver/auth/verify-otp",
        json={"phone": phone, "code": debug_otp, "name": "Admin Test Driver"},
    )
    assert verify.status_code == 200, verify.text
    body = api_json(verify)
    return body["access_token"], body["driver_id"]


def _submit_driver_application(client: TestClient) -> tuple[str, str]:
    token, driver_id = _register_driver(client)
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.post(
        f"{API}/driver/profile",
        headers=headers,
        json={
            "vehicle_model": "Swift",
            "vehicle_plate": "KA01ZZ9999",
            "vehicle_color": "White",
            "name": "Admin Test Driver",
        },
    )
    assert profile.status_code == 201, profile.text

    confirm = client.post(
        f"{API}/driver/documents/confirm",
        headers=headers,
        json={
            "document_type": "license",
            "file_key": f"drivers/{driver_id}/license/test-file",
        },
    )
    assert confirm.status_code == 201, confirm.text

    vehicle = client.post(
        f"{API}/driver/onboarding/vehicle",
        headers=headers,
        json={
            "vehicle_type": "cab",
            "make": "Maruti",
            "model": "Swift",
            "year": 2022,
            "plate_number": "KA01ZZ9999",
            "color": "White",
        },
    )
    assert vehicle.status_code == 201, vehicle.text

    submit = client.post(f"{API}/driver/onboarding/submit", headers=headers)
    assert submit.status_code == 200, submit.text
    assert api_json(submit)["onboarding_status"] == "under_review"

    return token, driver_id


def test_admin_driver_kyc_review_flow(client: TestClient) -> None:
    driver_token, driver_id = _submit_driver_application(client)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    blocked = client.patch(
        f"{API}/driver/status",
        headers=driver_headers,
        json={"status": "online", "latitude": "12.9700", "longitude": "77.5900"},
    )
    assert blocked.status_code == 400, blocked.text
    assert "KYC_NOT_APPROVED" in blocked.text

    wrong_key = client.get(
        f"{API}/admin/driver-applications",
        headers={"X-Admin-Key": "wrong-key"},
    )
    api_error(wrong_key, status_code=401)

    listing = client.get(
        f"{API}/admin/driver-applications",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    apps = api_json(listing)
    assert apps["total"] >= 1
    assert any(app["driver_id"] == driver_id for app in apps["applications"])

    detail = client.get(
        f"{API}/admin/driver-applications/{driver_id}",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    detail_data = api_json(detail)
    assert detail_data["driver_id"] == driver_id
    assert detail_data["onboarding_status"] == "under_review"
    assert len(detail_data["documents"]) == 1
    assert detail_data["documents"][0]["view_url"]

    approve = client.post(
        f"{API}/admin/driver-applications/{driver_id}/approve",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    approved = api_json(approve)
    assert approved["kyc_status"] == "approved"
    assert approved["onboarding_status"] == "approved"

    go_online = client.patch(
        f"{API}/driver/status",
        headers=driver_headers,
        json={"status": "online", "latitude": "12.9700", "longitude": "77.5900"},
    )
    assert go_online.status_code == 200, go_online.text
    assert api_json(go_online)["status"] == "online"


def test_admin_reject_driver_application(client: TestClient) -> None:
    _, driver_id = _submit_driver_application(client)

    reject = client.post(
        f"{API}/admin/driver-applications/{driver_id}/reject",
        headers={"X-Admin-Key": ADMIN_KEY},
        json={"reason": "Documents are unclear"},
    )
    rejected = api_json(reject)
    assert rejected["kyc_status"] == "rejected"
    assert rejected["onboarding_status"] == "rejected"

    detail = client.get(
        f"{API}/admin/driver-applications/{driver_id}",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    detail_data = api_json(detail)
    assert detail_data["kyc_status"] == "rejected"
    assert detail_data["documents"][0]["rejection_reason"] == "Documents are unclear"
