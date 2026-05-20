from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.models.ride import FareRule, RideType


async def get_ride_type_by_slug(db: AsyncSession, slug: str) -> RideType:
    result = await db.execute(select(RideType).where(RideType.slug == slug, RideType.is_active.is_(True)))
    ride_type = result.scalar_one_or_none()
    if ride_type is None:
        raise not_found(f"Ride type '{slug}' not found", "RIDE_TYPE_NOT_FOUND")
    return ride_type


async def get_fare_rule(db: AsyncSession, ride_type_id: UUID) -> FareRule:
    result = await db.execute(
        select(FareRule).where(FareRule.ride_type_id == ride_type_id, FareRule.is_active.is_(True))
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise not_found("Fare rule not configured", "FARE_RULE_NOT_FOUND")
    return rule


def calculate_fare(
    rule: FareRule,
    distance_km: Decimal,
    duration_min: Decimal,
    surge_multiplier: Decimal = Decimal("1.00"),
) -> Decimal:
    fare = rule.base_fare + (distance_km * rule.per_km_rate) + (duration_min * rule.per_min_rate)
    fare = fare * surge_multiplier
    if fare < rule.minimum_fare:
        fare = rule.minimum_fare
    return fare.quantize(Decimal("0.01"))
