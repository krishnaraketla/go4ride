from decimal import Decimal

import pytest

from app.services.geo_service import (
    RouteInfo,
    _haversine_estimate,
    get_driving_eta_min,
    get_route,
    haversine_distance_m,
)


def test_haversine_distance_m() -> None:
    distance_m = haversine_distance_m(
        Decimal("12.9716"), Decimal("77.5946"), Decimal("12.9700"), Decimal("77.5900")
    )
    assert distance_m > 0
    assert distance_m < 2000


@pytest.mark.asyncio
async def test_get_driving_eta_min_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "mock")
    from app.core.config import get_settings

    get_settings.cache_clear()
    eta = await get_driving_eta_min(
        Decimal("12.9716"),
        Decimal("77.5946"),
        Decimal("12.9352"),
        Decimal("77.6245"),
    )
    assert eta is not None
    assert eta >= 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_google_distance_matrix_eta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "google")
    monkeypatch.setenv("MAPS_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    class FakeResponse:
        def json(self):
            return {
                "status": "OK",
                "rows": [
                    {
                        "elements": [
                            {
                                "status": "OK",
                                "duration_in_traffic": {"value": 420},
                            }
                        ]
                    }
                ],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.geo_service.httpx.AsyncClient", lambda **kwargs: FakeClient())
    eta = await get_driving_eta_min(
        Decimal("12.9716"),
        Decimal("77.5946"),
        Decimal("12.9700"),
        Decimal("77.5900"),
    )
    assert eta == 7
    get_settings.cache_clear()


def test_haversine_returns_positive_distance():
    distance_km, duration_min = _haversine_estimate(
        Decimal("12.9716"), Decimal("77.5946"), Decimal("12.9352"), Decimal("77.6245")
    )
    assert distance_km > 0
    assert duration_min > 0


@pytest.mark.asyncio
async def test_get_route_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPS_PROVIDER", "mock")
    from app.core.config import get_settings

    get_settings.cache_clear()
    route = await get_route(
        Decimal("12.9716"),
        Decimal("77.5946"),
        Decimal("12.9352"),
        Decimal("77.6245"),
    )
    assert isinstance(route, RouteInfo)
    assert route.distance_km > 0
    assert route.duration_min > 0
    assert route.polyline is None
    get_settings.cache_clear()
