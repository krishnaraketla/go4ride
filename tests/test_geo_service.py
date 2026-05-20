from decimal import Decimal

from app.services.geo_service import _haversine_estimate


def test_haversine_returns_positive_distance():
    distance_km, duration_min = _haversine_estimate(
        Decimal("12.9716"), Decimal("77.5946"), Decimal("12.9352"), Decimal("77.6245")
    )
    assert distance_km > 0
    assert duration_min > 0
