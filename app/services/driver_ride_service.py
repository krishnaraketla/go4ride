"""Driver ride service — all ride operations performed by a driver."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import bad_request, forbidden, not_found
from app.models.driver import DriverProfile
from app.models.enums import DriverStatus, RideStatus
from app.models.ride import Ride
from app.models.user import User
from app.schemas.driver import (
    DriverRideResponse,
    DriverRideSearchItem,
    DriverRideSearchMeta,
    DriverRideSearchResponse,
    RiderSummary,
)
from app.services import geo_service
from app.services.ride_service import TERMINAL_STATUSES, transition_ride

# Statuses where the driver is actively managing a ride
_ACTIVE_STATUSES = {
    RideStatus.driver_assigned,
    RideStatus.driver_arrived,
    RideStatus.in_progress,
}


async def search_nearby_rides(
    db: AsyncSession,
    driver: User,
    lat: Decimal,
    lng: Decimal,
    radius_km: float,
    limit: int,
) -> DriverRideSearchResponse:
    """Return open rides whose pickup is within radius_km of the driver."""
    profile = await _get_driver_profile(db, driver.id)
    if profile.driver_status == DriverStatus.offline:
        raise bad_request("Driver must be online to search for rides", "DRIVER_OFFLINE")
    if profile.driver_status == DriverStatus.on_ride:
        settings = get_settings()
        return DriverRideSearchResponse(
            rides=[],
            search=DriverRideSearchMeta(
                lat=lat, lng=lng, radius_km=radius_km, total=0
            ),
        )

    radius_m = int(radius_km * 1000)
    result = await db.execute(
        select(Ride)
        .where(Ride.status == RideStatus.searching_driver)
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.requested_at.asc())
    )
    rides = result.scalars().all()

    matched: list[tuple[int, Ride]] = []
    for ride in rides:
        distance_m = geo_service.haversine_distance_m(lat, lng, ride.pickup_lat, ride.pickup_lng)
        if distance_m <= radius_m:
            matched.append((distance_m, ride))

    matched.sort(key=lambda item: (item[0], item[1].requested_at))
    matched = matched[:limit]

    items: list[DriverRideSearchItem] = []
    for distance_m, ride in matched:
        base = await _to_driver_ride_response(db, ride)
        pickup_eta = await geo_service.get_driving_eta_min(lat, lng, ride.pickup_lat, ride.pickup_lng)
        items.append(
            DriverRideSearchItem(
                **base.model_dump(),
                pickup_distance_m=distance_m,
                pickup_eta_min=pickup_eta,
            )
        )

    return DriverRideSearchResponse(
        rides=items,
        search=DriverRideSearchMeta(lat=lat, lng=lng, radius_km=radius_km, total=len(items)),
    )


async def get_pending_ride(db: AsyncSession, driver: User) -> DriverRideResponse | None:
    """Deprecated: use search_nearby_rides. Returns nearest ride within default radius."""
    profile = await _get_driver_profile(db, driver.id)
    if profile.current_lat is None or profile.current_lng is None:
        raise bad_request("Driver location required. Call PATCH /driver/status or /driver/location first.", "LOCATION_REQUIRED")
    settings = get_settings()
    search = await search_nearby_rides(
        db,
        driver,
        profile.current_lat,
        profile.current_lng,
        settings.driver_search_default_radius_km,
        1,
    )
    if not search.rides:
        return None
    return search.rides[0]


async def accept_ride(db: AsyncSession, driver: User, ride_id: UUID) -> DriverRideResponse:
    """Driver accepts a ride — transitions to driver_assigned."""
    profile = await _get_driver_profile(db, driver.id)
    if profile.driver_status != DriverStatus.online:
        raise bad_request("Driver must be online to accept rides", "DRIVER_OFFLINE")

    # Assign driver and transition
    ride = await transition_ride(
        db,
        ride_id,
        RideStatus.driver_assigned,
        driver_id=driver.id,
        message="Driver accepted the ride",
    )

    # Mark driver as on-ride
    profile.driver_status = DriverStatus.on_ride
    await db.flush()

    return await _to_driver_ride_response(db, ride)


async def reject_ride(db: AsyncSession, driver: User, ride_id: UUID) -> dict:
    """Driver rejects a ride — ride goes back to searching (no status change in this model)."""
    result = await db.execute(
        select(Ride).where(Ride.id == ride_id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    if ride.status != RideStatus.searching_driver:
        raise bad_request("Ride is no longer available", "RIDE_NOT_AVAILABLE")
    return {"ride_id": ride_id, "status": ride.status.value, "message": "Ride rejected"}


async def arrived_at_pickup(db: AsyncSession, driver: User, ride_id: UUID) -> DriverRideResponse:
    """Driver marks arrival at pickup — transitions to driver_arrived and generates OTP."""
    await _assert_driver_owns_ride(db, driver.id, ride_id)
    ride = await transition_ride(
        db,
        ride_id,
        RideStatus.driver_arrived,
        message="Driver arrived at pickup",
    )
    return await _to_driver_ride_response(db, ride)


async def start_ride(
    db: AsyncSession, driver: User, ride_id: UUID, otp: str
) -> DriverRideResponse:
    """Driver starts the ride after verifying the rider's OTP."""
    await _assert_driver_owns_ride(db, driver.id, ride_id)

    result = await db.execute(
        select(Ride).where(Ride.id == ride_id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    if ride.status != RideStatus.driver_arrived:
        raise bad_request(
            f"Cannot start ride from status {ride.status.value}", "INVALID_RIDE_STATE"
        )
    if ride.start_otp != otp:
        raise bad_request("Invalid OTP", "INVALID_OTP")

    ride = await transition_ride(
        db,
        ride_id,
        RideStatus.in_progress,
        message="Ride started",
    )
    return await _to_driver_ride_response(db, ride)


async def complete_ride(db: AsyncSession, driver: User, ride_id: UUID) -> DriverRideResponse:
    """Driver marks the ride as completed."""
    await _assert_driver_owns_ride(db, driver.id, ride_id)
    ride = await transition_ride(
        db,
        ride_id,
        RideStatus.completed,
        message="Ride completed",
    )

    # Mark driver back as online
    profile = await _get_driver_profile(db, driver.id)
    profile.driver_status = DriverStatus.online
    profile.total_rides = (profile.total_rides or 0) + 1
    await db.flush()

    return await _to_driver_ride_response(db, ride)


async def get_current_ride(db: AsyncSession, driver: User) -> DriverRideResponse | None:
    """Return the driver's active ride, if any."""
    result = await db.execute(
        select(Ride)
        .where(Ride.driver_id == driver.id, Ride.status.in_(_ACTIVE_STATUSES))
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.driver_assigned_at.desc())
        .limit(1)
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        return None
    return await _to_driver_ride_response(db, ride)


async def get_driver_ride_history(
    db: AsyncSession,
    driver: User,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[DriverRideResponse], int]:
    offset = (page - 1) * limit
    conditions = [
        Ride.driver_id == driver.id,
        Ride.status.in_(TERMINAL_STATUSES),
    ]
    count_result = await db.execute(
        select(func.count()).select_from(Ride).where(*conditions)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Ride)
        .where(*conditions)
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.completed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rides = result.scalars().all()
    responses = [await _to_driver_ride_response(db, r) for r in rides]
    return responses, total


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_driver_profile(db: AsyncSession, driver_id: UUID) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise bad_request("Driver profile not found. Complete onboarding first.", "PROFILE_NOT_FOUND")
    return profile


async def _assert_driver_owns_ride(db: AsyncSession, driver_id: UUID, ride_id: UUID) -> None:
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    if ride.driver_id != driver_id:
        raise forbidden("Not your ride")


async def _rider_summary(db: AsyncSession, rider_id: UUID) -> RiderSummary | None:
    from app.models.user import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == rider_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return RiderSummary(id=user.id, name=user.name, phone=user.phone)


async def _to_driver_ride_response(db: AsyncSession, ride: Ride) -> DriverRideResponse:
    slug = ride.ride_type.slug if ride.ride_type else None
    rider = await _rider_summary(db, ride.rider_id)
    return DriverRideResponse(
        id=ride.id,
        status=ride.status.value,
        pickup_lat=ride.pickup_lat,
        pickup_lng=ride.pickup_lng,
        pickup_address=ride.pickup_address,
        drop_lat=ride.drop_lat,
        drop_lng=ride.drop_lng,
        drop_address=ride.drop_address,
        estimated_fare=ride.estimated_fare,
        final_fare=ride.final_fare,
        distance_km=ride.distance_km,
        duration_min=ride.duration_min,
        surge_multiplier=ride.surge_multiplier,
        ride_type_slug=slug,
        start_otp=ride.start_otp,
        requested_at=ride.requested_at,
        driver_assigned_at=ride.driver_assigned_at,
        driver_arrived_at=ride.driver_arrived_at,
        started_at=ride.started_at,
        completed_at=ride.completed_at,
        cancelled_at=ride.cancelled_at,
        rider=rider,
    )
