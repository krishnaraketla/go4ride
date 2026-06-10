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

REQUIRED_DOCS = ("license", "registration", "insurance", "profile_photo")


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
    assert body["onboarding_status"] == "step1"
    assert body["profile_status"] is False
    return body["access_token"], body["driver_id"]


def _get_city_id(client: TestClient, headers: dict[str, str]) -> str:
    cities = client.get(f"{API}/driver/cities", headers=headers)
    assert cities.status_code == 200, cities.text
    data = api_json(cities)
    assert len(data) >= 1
    return data[0]["id"]


def _upload_all_documents(client: TestClient, headers: dict[str, str], driver_id: str) -> None:
    for doc_type in REQUIRED_DOCS:
        confirm = client.post(
            f"{API}/driver/documents/confirm",
            headers=headers,
            json={
                "document_type": doc_type,
                "file_key": f"drivers/{driver_id}/{doc_type}/test-file",
            },
        )
        assert confirm.status_code == 201, confirm.text

    status = client.get(f"{API}/driver/onboarding/status", headers=headers)
    assert status.status_code == 200, status.text
    assert api_json(status)["onboarding_status"] == "step2"


def _submit_vehicle(client: TestClient, headers: dict[str, str], driver_id: str) -> None:
    city_id = _get_city_id(client, headers)
    photos = {
        side: f"drivers/{driver_id}/vehicle-photos/{side}/test-file"
        for side in ("front", "back", "left", "right")
    }
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
            "city_id": city_id,
            "photos": photos,
        },
    )
    assert vehicle.status_code == 201, vehicle.text


def _submit_driver_application(client: TestClient) -> tuple[str, str]:
    token, driver_id = _register_driver(client)
    headers = {"Authorization": f"Bearer {token}"}

    _upload_all_documents(client, headers, driver_id)
    _submit_vehicle(client, headers, driver_id)

    submit = client.post(f"{API}/driver/onboarding/submit", headers=headers)
    assert submit.status_code == 200, submit.text
    submit_data = api_json(submit)
    assert submit_data["onboarding_status"] == "application_submitted"
    assert submit_data["profile_status"] is False
    assert submit_data["estimated_review_time"] == "15 minutes"
    assert submit_data["application_id"]

    return token, driver_id


def test_admin_driver_kyc_review_flow(client: TestClient) -> None:
    driver_token, driver_id = _submit_driver_application(client)
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    face_confirm = client.post(
        f"{API}/driver/onboarding/face-verification/confirm",
        headers=driver_headers,
        json={"file_key": f"drivers/{driver_id}/face-verification/test-file"},
    )
    assert face_confirm.status_code == 200, face_confirm.text
    assert api_json(face_confirm)["face_verification_completed"] is True

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
    assert detail_data["onboarding_status"] == "application_submitted"
    assert len(detail_data["documents"]) == 4
    assert detail_data["documents"][0]["view_url"]
    assert detail_data["city_name"]
    assert detail_data["vehicle_photos"]["front"]

    approve = client.post(
        f"{API}/admin/driver-applications/{driver_id}/approve",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    approved = api_json(approve)
    assert approved["kyc_status"] == "approved"
    assert approved["onboarding_status"] == "kyc_approved"

    status = client.get(f"{API}/driver/onboarding/status", headers=driver_headers)
    assert api_json(status)["profile_status"] is True

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
    assert rejected["onboarding_status"] == "kyc_rejected"

    detail = client.get(
        f"{API}/admin/driver-applications/{driver_id}",
        headers={"X-Admin-Key": ADMIN_KEY},
    )
    detail_data = api_json(detail)
    assert detail_data["kyc_status"] == "rejected"
    assert detail_data["kyc_rejection_reason"] == "Documents are unclear"
    assert detail_data["documents"][0]["rejection_reason"] == "Documents are unclear"
