"""Helpers for integration tests against the standard API envelope."""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient


def api_json(response) -> Any:
    assert response.status_code < 400, response.text
    body = response.json()
    assert body.get("success") is True, body
    return body["data"]


def api_error(response, *, status_code: int) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body.get("success") is False, body
    assert "message" in body
    assert body.get("data") is not None
    assert "code" in body["data"]
    return body
