from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import bad_request, not_found
from app.core.redis import get_idempotency, publish_ride_event, store_idempotency
from app.models.enums import RideStatus
from app.models.ride import Ride, RideStatusEvent
from app.models.user import User
from app.schemas.ride import CreateRideRequest, RideResponse, RideStatusResponse
from app.services import fare_service, geo_service

# Phase 1: cancel only before a driver takes the trip (stays at searching_driver)
CANCELLABLE = {RideStatus.requested, RideStatus.searching_driver}


async def estimate_ride(
    db: AsyncSession,
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    drop_lat: Decimal,
    drop_lng: Decimal,
    ride_type_slug: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    ride_type = await fare_service.get_ride_type_by_slug(db, ride_type_slug)
    rule = await fare_service.get_fare_rule(db, ride_type.id)
    distance_km, duration_min = await geo_service.get_route_distance_duration(
        pickup_lat, pickup_lng, drop_lat, drop_lng
    )
    surge = Decimal("1.00")
    estimated = fare_service.calculate_fare(rule, distance_km, duration_min, surge)
    return distance_km, duration_min, estimated, surge, rule.currency


async def create_ride(
    db: AsyncSession,
    rider: User,
    body: CreateRideRequest,
    idempotency_key: str | None = None,
) -> RideResponse:
    if idempotency_key:
        cached = await get_idempotency(idempotency_key)
        if cached:
            return RideResponse.model_validate_json(cached)

    ride_type = await fare_service.get_ride_type_by_slug(db, body.ride_type_slug)
    distance_km, duration_min, estimated, surge, _ = await estimate_ride(
        db, body.pickup.lat, body.pickup.lng, body.drop.lat, body.drop.lng, body.ride_type_slug
    )

    ride = Ride(
        rider_id=rider.id,
        ride_type_id=ride_type.id,
        status=RideStatus.requested,
        pickup_lat=body.pickup.lat,
        pickup_lng=body.pickup.lng,
        pickup_address=body.pickup_address,
        drop_lat=body.drop.lat,
        drop_lng=body.drop.lng,
        drop_address=body.drop_address,
        distance_km=distance_km,
        duration_min=duration_min,
        estimated_fare=estimated,
        surge_multiplier=surge,
    )
    db.add(ride)
    await db.flush()
    await _record_status(db, ride, RideStatus.requested, "Ride requested")
    # Phase 1 stub: no driver matching — ride stays at searching_driver
    await _transition_status(db, ride, RideStatus.searching_driver, "Searching for driver")

    result = await db.execute(
        select(Ride).where(Ride.id == ride.id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one()
    response = _to_ride_response(ride)

    if idempotency_key:
        await store_idempotency(idempotency_key, response.model_dump_json())

    return response


async def cancel_ride(db: AsyncSession, rider: User, ride_id: UUID) -> RideResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    if ride.status not in CANCELLABLE:
        raise bad_request("Ride cannot be cancelled", "RIDE_NOT_CANCELLABLE")
    await _transition_status(db, ride, RideStatus.cancelled, "Cancelled by rider")
    ride.cancelled_at = datetime.now(timezone.utc)
    return _to_ride_response(ride)


async def get_ride(db: AsyncSession, rider: User, ride_id: UUID) -> RideResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    return _to_ride_response(ride)


async def get_ride_status(db: AsyncSession, rider: User, ride_id: UUID) -> RideStatusResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    return RideStatusResponse(id=ride.id, status=ride.status.value)


async def get_ride_history(
    db: AsyncSession, rider: User, page: int = 1, limit: int = 20
) -> tuple[list[RideResponse], int]:
    offset = (page - 1) * limit
    count_result = await db.execute(
        select(func.count()).select_from(Ride).where(Ride.rider_id == rider.id)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Ride)
        .where(Ride.rider_id == rider.id)
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rides = result.scalars().all()
    return [_to_ride_response(r) for r in rides], total


async def _get_ride_for_rider(db: AsyncSession, rider_id: UUID, ride_id: UUID) -> Ride:
    result = await db.execute(
        select(Ride).where(Ride.id == ride_id, Ride.rider_id == rider_id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    return ride


async def _record_status(
    db: AsyncSession, ride: Ride, status: RideStatus, message: str | None = None
) -> RideStatusEvent:
    event = RideStatusEvent(ride_id=ride.id, status=status, message=message)
    db.add(event)
    await db.flush()
    await publish_ride_event(
        str(ride.id),
        {
            "ride_id": str(ride.id),
            "status": status.value,
            "message": message,
            "created_at": event.created_at.isoformat(),
        },
    )
    return event


async def _transition_status(
    db: AsyncSession, ride: Ride, status: RideStatus, message: str | None = None
) -> None:
    ride.status = status
    now = datetime.now(timezone.utc)
    if status == RideStatus.cancelled:
        ride.cancelled_at = now
    await _record_status(db, ride, status, message)


def _to_ride_response(ride: Ride) -> RideResponse:
    slug = ride.ride_type.slug if ride.ride_type else None
    return RideResponse(
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
        requested_at=ride.requested_at,
        driver_assigned_at=ride.driver_assigned_at,
        driver_arrived_at=ride.driver_arrived_at,
        started_at=ride.started_at,
        completed_at=ride.completed_at,
        cancelled_at=ride.cancelled_at,
    )
