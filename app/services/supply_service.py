"""Mock driver supply for ride quotes (Phase 1.5)."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.driver import DriverProfile
from app.services.geo_service import haversine_distance_m


@dataclass(frozen=True)
class SupplyInfo:
    available: bool
    drivers_nearby: int
    pickup_eta_min: int | None


async def mock_availability(
    db: AsyncSession,
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    *,
    ride_type_slug: str,
) -> SupplyInfo:
    """Phase 1.5: mock nearby drivers and pickup ETA until real matching exists."""
    _ = ride_type_slug
    settings = get_settings()
    result = await db.execute(
        select(DriverProfile).where(
            DriverProfile.current_lat.isnot(None),
            DriverProfile.current_lng.isnot(None),
        )
    )
    profiles = result.scalars().all()
    count_result = await db.execute(select(func.count()).select_from(DriverProfile))
    total_drivers = count_result.scalar() or 0
    drivers_nearby = len(profiles) if profiles else max(1, total_drivers)

    if not profiles:
        return SupplyInfo(
            available=True,
            drivers_nearby=drivers_nearby,
            pickup_eta_min=settings.mock_driver_eta_min,
        )

    nearest_m = min(
        haversine_distance_m(pickup_lat, pickup_lng, p.current_lat, p.current_lng)  # type: ignore[arg-type]
        for p in profiles
    )
    # Assume ~25 km/h average for pickup leg
    pickup_eta = max(3, int(round(nearest_m / 1000 / 25 * 60)))
    return SupplyInfo(
        available=True,
        drivers_nearby=drivers_nearby,
        pickup_eta_min=pickup_eta,
    )
