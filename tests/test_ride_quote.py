"""Integration tests for POST /rides/quote."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from app.core.redis import close_redis
from app.main import app
from tests.api_helpers import api_json

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
def client() -> TestClient:
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


def test_quote_returns_all_ride_types(client: TestClient) -> None:
    resp = client.post(f"{API}/rides/quote", json={"pickup": PICKUP, "drop": DROP})
    assert resp.status_code == 200, resp.text
    body = api_json(resp)
    assert body["pickup_address"]
    assert body["drop_address"]
    assert body["route"]["distance_km"] > 0
    slugs = {opt["slug"] for opt in body["options"]}
    assert slugs >= {"mini", "sedan", "bike", "xl"}
    for opt in body["options"]:
        assert opt["estimated_fare"] > 0
        assert opt["trip_duration_min"] > 0
        if opt["available"]:
            assert opt["total_eta_min"] is not None


def test_obsolete_booking_endpoints_removed(client: TestClient) -> None:
    assert client.get(f"{API}/ride-types").status_code == 404
    assert client.post(
        f"{API}/rides/estimate",
        json={"pickup": PICKUP, "drop": DROP, "ride_type_slug": "mini"},
    ).status_code == 404
