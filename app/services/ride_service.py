import secrets
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.core.redis import get_idempotency, publish_ride_event, store_idempotency
from app.models.driver import DriverProfile
from app.models.enums import RideStatus
from app.models.ride import Ride, RideStatusEvent
from app.models.user import User
from app.core.config import get_settings as get_app_settings
from app.schemas.invoice import InvoiceResponse
from app.schemas.ride import (
    Coordinates,
    CreateRideRequest,
    DriverSummary,
    RepeatRideResponse,
    RideResponse,
    RideStatusResponse,
)
from app.services import fare_service, geo_service

TERMINAL_STATUSES = {RideStatus.completed, RideStatus.cancelled}

VALID_TRANSITIONS: dict[RideStatus, set[RideStatus]] = {
    RideStatus.requested: {RideStatus.searching_driver},
    RideStatus.searching_driver: {RideStatus.driver_assigned, RideStatus.cancelled},
    RideStatus.driver_assigned: {RideStatus.driver_arrived, RideStatus.cancelled},
    RideStatus.driver_arrived: {RideStatus.in_progress, RideStatus.cancelled},
    RideStatus.in_progress: {RideStatus.completed},
    RideStatus.completed: set(),
    RideStatus.cancelled: set(),
}

CANCELLABLE = {
    RideStatus.requested,
    RideStatus.searching_driver,
    RideStatus.driver_assigned,
    RideStatus.driver_arrived,
}

_DRIVER_WS_STATUSES = {
    RideStatus.driver_assigned,
    RideStatus.driver_arrived,
    RideStatus.in_progress,
    RideStatus.completed,
}


def assert_valid_transition(current: RideStatus, target: RideStatus) -> None:
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise bad_request(
            f"Cannot transition from {current.value} to {target.value}",
            "INVALID_RIDE_TRANSITION",
        )


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
    await _transition_status(db, ride, RideStatus.searching_driver, "Searching for driver")

    result = await db.execute(
        select(Ride).where(Ride.id == ride.id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one()
    response = await _to_ride_response(db, ride)

    if idempotency_key:
        await store_idempotency(idempotency_key, response.model_dump_json())

    settings = get_settings()
    if settings.mock_driver_enabled:
        from app.services.mock_driver_service import schedule_mock_lifecycle

        schedule_mock_lifecycle(ride.id)

    return response


async def cancel_ride(db: AsyncSession, rider: User, ride_id: UUID) -> RideResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    if ride.status not in CANCELLABLE:
        raise bad_request("Ride cannot be cancelled", "RIDE_NOT_CANCELLABLE")
    await _transition_status(db, ride, RideStatus.cancelled, "Cancelled by rider")
    return await _to_ride_response(db, ride)


async def get_ride(db: AsyncSession, rider: User, ride_id: UUID) -> RideResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    return await _to_ride_response(db, ride)


async def get_ride_status(db: AsyncSession, rider: User, ride_id: UUID) -> RideStatusResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    message = await _latest_status_message(db, ride.id)
    driver = await _driver_summary_for_ride(db, ride)
    return RideStatusResponse(
        id=ride.id,
        status=ride.status.value,
        message=message,
        driver=driver,
    )


def _history_status_clause(status: str | None):
    """Build SQLAlchemy filter for ride history status query param."""
    if status is None or status == "terminal":
        return Ride.status.in_(TERMINAL_STATUSES)
    if status == "all":
        return None
    if status == "completed":
        return Ride.status == RideStatus.completed
    if status == "cancelled":
        return Ride.status == RideStatus.cancelled
    raise bad_request(
        "Invalid status filter. Use terminal, all, completed, or cancelled",
        "INVALID_STATUS_FILTER",
    )


def _invoice_available(ride: Ride) -> bool:
    return ride.status == RideStatus.completed and ride.final_fare is not None


async def get_ride_invoice(db: AsyncSession, rider: User, ride_id: UUID) -> InvoiceResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    settings = get_app_settings()
    if ride.status != RideStatus.completed or ride.final_fare is None:
        return InvoiceResponse(available=False)
    driver = await _driver_summary_for_ride(db, ride)
    return InvoiceResponse(
        available=True,
        ride_id=ride.id,
        status=ride.status.value,
        pickup_address=ride.pickup_address,
        drop_address=ride.drop_address,
        final_fare=ride.final_fare,
        currency=settings.default_currency,
        completed_at=ride.completed_at,
        driver=driver,
        download_url=f"/api/v1/rides/{ride.id}/invoice/download",
    )


async def get_repeat_ride_payload(
    db: AsyncSession, rider: User, ride_id: UUID
) -> RepeatRideResponse:
    ride = await _get_ride_for_rider(db, rider.id, ride_id)
    slug = ride.ride_type.slug if ride.ride_type else "mini"
    return RepeatRideResponse(
        pickup=Coordinates(lat=ride.pickup_lat, lng=ride.pickup_lng),
        drop=Coordinates(lat=ride.drop_lat, lng=ride.drop_lng),
        pickup_address=ride.pickup_address,
        drop_address=ride.drop_address,
        ride_type_slug=slug,
    )


async def get_ride_history(
    db: AsyncSession,
    rider: User,
    page: int = 1,
    limit: int = 20,
    status: str | None = "terminal",
) -> tuple[list[RideResponse], int]:
    offset = (page - 1) * limit
    conditions = [Ride.rider_id == rider.id]
    status_clause = _history_status_clause(status)
    if status_clause is not None:
        conditions.append(status_clause)
    count_result = await db.execute(
        select(func.count()).select_from(Ride).where(*conditions)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Ride)
        .where(*conditions)
        .options(selectinload(Ride.ride_type))
        .order_by(Ride.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rides = result.scalars().all()
    responses = []
    for ride in rides:
        responses.append(await _to_ride_response(db, ride))
    return responses, total


async def transition_ride(
    db: AsyncSession,
    ride_id: UUID,
    to_status: RideStatus,
    *,
    driver_id: UUID | None = None,
    message: str | None = None,
) -> Ride:
    result = await db.execute(
        select(Ride).where(Ride.id == ride_id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    if ride.status in TERMINAL_STATUSES:
        return ride
    assert_valid_transition(ride.status, to_status)
    if driver_id is not None:
        ride.driver_id = driver_id
    await _transition_status(db, ride, to_status, message)
    return ride


async def _get_ride_for_rider(db: AsyncSession, rider_id: UUID, ride_id: UUID) -> Ride:
    result = await db.execute(
        select(Ride).where(Ride.id == ride_id, Ride.rider_id == rider_id).options(selectinload(Ride.ride_type))
    )
    ride = result.scalar_one_or_none()
    if ride is None:
        raise not_found("Ride not found", "RIDE_NOT_FOUND")
    return ride


async def _latest_status_message(db: AsyncSession, ride_id: UUID) -> str | None:
    result = await db.execute(
        select(RideStatusEvent.message)
        .where(RideStatusEvent.ride_id == ride_id)
        .order_by(RideStatusEvent.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _driver_summary_for_ride(db: AsyncSession, ride: Ride) -> DriverSummary | None:
    if ride.driver_id is None:
        return None
    user_result = await db.execute(select(User).where(User.id == ride.driver_id))
    driver_user = user_result.scalar_one_or_none()
    if driver_user is None:
        return None
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == ride.driver_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        return None
    settings = get_settings()
    return DriverSummary(
        id=driver_user.id,
        name=driver_user.name or "Driver",
        phone=driver_user.phone,
        vehicle_model=profile.vehicle_model,
        vehicle_plate=profile.vehicle_plate,
        vehicle_color=profile.vehicle_color,
        lat=profile.current_lat,
        lng=profile.current_lng,
        eta_min=(
            settings.mock_driver_eta_min
            if ride.status in {RideStatus.driver_assigned, RideStatus.driver_arrived}
            else None
        ),
    )


async def _record_status(
    db: AsyncSession, ride: Ride, status: RideStatus, message: str | None = None
) -> RideStatusEvent:
    event = RideStatusEvent(ride_id=ride.id, status=status, message=message)
    db.add(event)
    await db.flush()
    payload: dict = {
        "ride_id": str(ride.id),
        "status": status.value,
        "message": message,
        "created_at": event.created_at.isoformat(),
    }
    if status in _DRIVER_WS_STATUSES and ride.driver_id is not None:
        driver = await _driver_summary_for_ride(db, ride)
        if driver is not None:
            payload["driver"] = driver.model_dump(mode="json")
    await publish_ride_event(str(ride.id), payload)
    return event


async def _transition_status(
    db: AsyncSession, ride: Ride, status: RideStatus, message: str | None = None
) -> None:
    if ride.status not in TERMINAL_STATUSES:
        assert_valid_transition(ride.status, status)
    ride.status = status
    now = datetime.now(timezone.utc)
    if status == RideStatus.driver_assigned:
        if ride.driver_id is None:
            raise bad_request("Driver required before assignment", "DRIVER_REQUIRED")
        ride.driver_assigned_at = now
    elif status == RideStatus.driver_arrived:
        ride.driver_arrived_at = now
    elif status == RideStatus.in_progress:
        ride.started_at = now
        ride.start_otp = f"{secrets.randbelow(1_000_000):06d}"
    elif status == RideStatus.completed:
        ride.completed_at = now
        ride.final_fare = ride.estimated_fare
    elif status == RideStatus.cancelled:
        ride.cancelled_at = now
    await _record_status(db, ride, status, message)


async def _to_ride_response(db: AsyncSession, ride: Ride) -> RideResponse:
    slug = ride.ride_type.slug if ride.ride_type else None
    driver = await _driver_summary_for_ride(db, ride)
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
        driver=driver,
        invoice_available=_invoice_available(ride),
    )
