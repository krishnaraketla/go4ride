from decimal import Decimal

from app.models.ride import FareRule
from app.services.fare_service import calculate_fare


def test_calculate_fare_minimum_applied():
    rule = FareRule(
        base_fare=Decimal("40"),
        per_km_rate=Decimal("12"),
        per_min_rate=Decimal("2"),
        minimum_fare=Decimal("100"),
    )
    fare = calculate_fare(rule, Decimal("1"), Decimal("1"))
    assert fare == Decimal("100.00")


def test_calculate_fare_with_surge():
    rule = FareRule(
        base_fare=Decimal("40"),
        per_km_rate=Decimal("10"),
        per_min_rate=Decimal("0"),
        minimum_fare=Decimal("40"),
    )
    fare = calculate_fare(rule, Decimal("5"), Decimal("0"), surge_multiplier=Decimal("1.5"))
    assert fare == Decimal("135.00")
