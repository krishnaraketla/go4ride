"""Unit tests for the driver API response envelope (no database required)."""

from fastapi.testclient import TestClient

from app.main import app
from tests.api_helpers import api_error

API = "/api/v1"


def test_driver_request_otp_validation_envelope() -> None:
    with TestClient(app) as client:
        resp = client.post(f"{API}/driver/auth/request-otp", json={"phone": "123"})
    body = api_error(resp, status_code=422)
    assert body["message"] == "Validation error"
    assert body["data"]["code"] == "VALIDATION_ERROR"
    assert body["data"]["errors"]


def test_driver_request_otp_envelope_shape() -> None:
    """OTP may fail without DB; we only assert envelope shape when it succeeds."""
    with TestClient(app) as client:
        resp = client.post(f"{API}/driver/auth/request-otp", json={"phone": "9876543210"})
    if resp.status_code == 200:
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "OTP sent"
        assert "expires_in_minutes" in body["data"]
        assert "is_new_user" in body["data"]
        assert "debug_otp" in body["data"] or body["data"].get("debug_otp") is None
    else:
        body = resp.json()
        assert body["success"] is False
        assert "message" in body
        assert body["data"]["code"]
