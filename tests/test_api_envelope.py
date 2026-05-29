"""Unit tests for the standard API response envelope (no database required)."""

from fastapi.testclient import TestClient

from app.main import app
from tests.api_helpers import api_error

API = "/api/v1"


def test_validation_error_envelope() -> None:
    with TestClient(app) as client:
        resp = client.post(f"{API}/auth/request-otp", json={"phone": "123"})
    body = api_error(resp, status_code=422)
    assert body["message"] == "Validation error"
    assert body["data"]["code"] == "VALIDATION_ERROR"
    assert body["data"]["errors"]


def test_request_otp_envelope_shape() -> None:
    """OTP may fail without DB; we only assert error envelope shape when it does."""
    with TestClient(app) as client:
        resp = client.post(f"{API}/auth/request-otp", json={"phone": "9876543210"})
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
