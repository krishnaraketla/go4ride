from decimal import Decimal

import pytest

from app.services.geo_service import (
    RouteInfo,
    _haversine_estimate,
    _parse_routes_duration_seconds,
    get_driving_eta_min,
    get_route,
    haversine_distance_m,
)


def test_haversine_distance_m() -> None:
    distance_m = haversine_distance_m(
        Decimal("37.7749"), Decimal("-122.4194"), Decimal("37.7739"), Decimal("-122.4184")
    )
    assert distance_m > 0
    assert distance_m < 2000


def test_parse_routes_duration_seconds() -> None:
    assert _parse_routes_duration_seconds("1349s") == 1349
    assert _parse_routes_duration_seconds("420s") == 420
    assert _parse_routes_duration_seconds("invalid") is None


@pytest.mark.asyncio
async def test_get_driving_eta_min_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "mock")
    from app.core.config import get_settings

    get_settings.cache_clear()
    eta = await get_driving_eta_min(
        Decimal("37.7749"),
        Decimal("-122.4194"),
        Decimal("37.7599"),
        Decimal("-122.4148"),
    )
    assert eta is not None
    assert eta >= 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_google_routes_eta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "google")
    monkeypatch.setenv("MAPS_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"routes": [{"duration": "420s"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.geo_service.httpx.AsyncClient", lambda **kwargs: FakeClient())
    eta = await get_driving_eta_min(
        Decimal("37.7749"),
        Decimal("-122.4194"),
        Decimal("37.7739"),
        Decimal("-122.4184"),
    )
    assert eta == 7
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_google_routes_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "google")
    monkeypatch.setenv("MAPS_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "routes": [
                    {
                        "distanceMeters": 6800,
                        "duration": "900s",
                        "polyline": {"encodedPolyline": "abc123"},
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.geo_service.httpx.AsyncClient", lambda **kwargs: FakeClient())
    route = await get_route(
        Decimal("37.7749"),
        Decimal("-122.4194"),
        Decimal("37.7599"),
        Decimal("-122.4148"),
    )
    assert isinstance(route, RouteInfo)
    assert route.distance_km == Decimal("6.8")
    assert route.duration_min == Decimal("15")
    assert route.polyline == "abc123"
    get_settings.cache_clear()


def test_haversine_returns_positive_distance():
    distance_km, duration_min = _haversine_estimate(
        Decimal("37.7749"), Decimal("-122.4194"), Decimal("37.7599"), Decimal("-122.4148")
    )
    assert distance_km > 0
    assert duration_min > 0


@pytest.mark.asyncio
async def test_get_route_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "mock")
    from app.core.config import get_settings

    get_settings.cache_clear()
    route = await get_route(
        Decimal("37.7749"),
        Decimal("-122.4194"),
        Decimal("37.7599"),
        Decimal("-122.4148"),
    )
    assert isinstance(route, RouteInfo)
    assert route.distance_km > 0
    assert route.duration_min > 0
    assert route.polyline is None
    get_settings.cache_clear()
