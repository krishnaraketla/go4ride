from decimal import Decimal

import pytest

from app.services.geo_service import RouteInfo, _haversine_estimate, get_route


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
