"""Live ride map payloads: ETA, polylines, and WebSocket events."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.redis import (
    get_cached_eta,
    get_cached_leg_polyline,
    publish_ride_event,
    set_cached_eta,
    set_cached_leg_polyline,
    should_publish_location_update,
)
from app.models.driver import DriverProfile
from app.models.enums import RideStatus
from app.models.ride import Ride
from app.models.user import User
from app.schemas.ride import DriverSummary
from app.services import geo_service

_ACTIVE_DRIVER_STATUSES = {
    RideStatus.driver_assigned,
    RideStatus.driver_arrived,
    RideStatus.in_progress,
}


async def get_active_ride_for_driver(db: AsyncSession, driver_id: UUID) -> Ride | None:
    result = await db.execute(
        select(Ride)
        .where(
            Ride.driver_id == driver_id,
            Ride.status.in_(_ACTIVE_DRIVER_STATUSES),
        )
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.driver_assigned_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_eta_for_ride(db: AsyncSession, ride: Ride, profile: DriverProfile) -> int | None:
    if profile.current_lat is None or profile.current_lng is None:
        return None
    if ride.status == RideStatus.driver_arrived:
        return 0
    if ride.status == RideStatus.driver_assigned:
        dest_lat, dest_lng = ride.pickup_lat, ride.pickup_lng
    elif ride.status == RideStatus.in_progress:
        dest_lat, dest_lng = ride.drop_lat, ride.drop_lng
    else:
        return None
    return await geo_service.get_driving_eta_min(
        profile.current_lat, profile.current_lng, dest_lat, dest_lng
    )


async def get_or_compute_eta(
    db: AsyncSession, ride: Ride, profile: DriverProfile
) -> int | None:
    settings = get_settings()
    cached = await get_cached_eta(str(ride.id))
    if cached is not None:
        return cached
    eta = await compute_eta_for_ride(db, ride, profile)
    if eta is not None:
        await set_cached_eta(str(ride.id), eta, settings.driver_eta_cache_ttl_sec)
    return eta


async def refresh_leg_polyline(db: AsyncSession, ride: Ride, profile: DriverProfile) -> str | None:
    if profile.current_lat is None or profile.current_lng is None:
        return None
    if ride.status == RideStatus.driver_assigned:
        origin_lat, origin_lng = profile.current_lat, profile.current_lng
        dest_lat, dest_lng = ride.pickup_lat, ride.pickup_lng
    elif ride.status == RideStatus.in_progress:
        origin_lat, origin_lng = profile.current_lat, profile.current_lng
        dest_lat, dest_lng = ride.drop_lat, ride.drop_lng
    else:
        return None
    polyline = await geo_service.get_route_polyline(origin_lat, origin_lng, dest_lat, dest_lng)
    if polyline:
        await set_cached_leg_polyline(str(ride.id), polyline)
    return polyline


async def driver_summary_for_ride(
    db: AsyncSession, ride: Ride, profile: DriverProfile | None = None
) -> DriverSummary | None:
    if ride.driver_id is None:
        return None
    user_result = await db.execute(select(User).where(User.id == ride.driver_id))
    driver_user = user_result.scalar_one_or_none()
    if driver_user is None:
        return None
    if profile is None:
        profile_result = await db.execute(
            select(DriverProfile).where(DriverProfile.user_id == ride.driver_id)
        )
        profile = profile_result.scalar_one_or_none()
    if profile is None:
        return None
    eta_min = None
    if ride.status in {
        RideStatus.driver_assigned,
        RideStatus.driver_arrived,
        RideStatus.in_progress,
    }:
        eta_min = await get_or_compute_eta(db, ride, profile)
    return DriverSummary(
        id=driver_user.id,
        name=driver_user.name or "Driver",
        phone=driver_user.phone,
        vehicle_model=profile.vehicle_model,
        vehicle_plate=profile.vehicle_plate,
        vehicle_color=profile.vehicle_color,
        lat=profile.current_lat,
        lng=profile.current_lng,
        eta_min=eta_min,
    )


async def build_status_payload(
    db: AsyncSession,
    ride: Ride,
    status: RideStatus,
    message: str | None,
    created_at: datetime,
) -> dict:
    payload: dict = {
        "type": "status",
        "ride_id": str(ride.id),
        "status": status.value,
        "message": message,
        "created_at": created_at.isoformat(),
        "route_polyline": ride.route_polyline,
    }
    if status in {
        RideStatus.driver_assigned,
        RideStatus.driver_arrived,
        RideStatus.in_progress,
        RideStatus.completed,
    } and ride.driver_id is not None:
        profile_result = await db.execute(
            select(DriverProfile).where(DriverProfile.user_id == ride.driver_id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is not None:
            driver = await driver_summary_for_ride(db, ride, profile)
            if driver is not None:
                payload["driver"] = driver.model_dump(mode="json")
            leg_polyline = await refresh_leg_polyline(db, ride, profile)
            if leg_polyline:
                payload["leg_polyline"] = leg_polyline
            else:
                cached_leg = await get_cached_leg_polyline(str(ride.id))
                if cached_leg:
                    payload["leg_polyline"] = cached_leg
    return payload


async def build_location_payload(db: AsyncSession, ride: Ride, profile: DriverProfile) -> dict:
    driver = await driver_summary_for_ride(db, ride, profile)
    leg_polyline = await get_cached_leg_polyline(str(ride.id))
    return {
        "type": "location_update",
        "ride_id": str(ride.id),
        "status": ride.status.value,
        "driver": driver.model_dump(mode="json") if driver else None,
        "route_polyline": ride.route_polyline,
        "leg_polyline": leg_polyline,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def publish_location_update(db: AsyncSession, driver_id: UUID) -> None:
    ride = await get_active_ride_for_driver(db, driver_id)
    if ride is None:
        return
    settings = get_settings()
    if not await should_publish_location_update(
        str(ride.id), settings.driver_location_publish_interval_sec
    ):
        return
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        return
    payload = await build_location_payload(db, ride, profile)
    await publish_ride_event(str(ride.id), payload)
