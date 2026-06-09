import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import bad_request, not_found
from app.core.redis import get_cached_leg_polyline, get_idempotency, publish_ride_event, store_idempotency
from app.models.enums import RideStatus
from app.models.ride import Ride, RideStatusEvent, RideType
from app.models.user import User
from app.schemas.invoice import InvoiceResponse
from app.schemas.ride import (
    Coordinates,
    CreateRideRequest,
    RepeatRideResponse,
    RideQuoteOption,
    RideQuoteResponse,
    RideResponse,
    RideStatusResponse,
    RouteSummary,
)
from app.services import fare_service, geo_service, ride_live_service, supply_service

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


def assert_valid_transition(current: RideStatus, target: RideStatus) -> None:
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise bad_request(
            f"Cannot transition from {current.value} to {target.value}",
            "INVALID_RIDE_TRANSITION",
        )


QUOTE_TTL_MINUTES = 5


def _trip_duration_min(duration_min: Decimal) -> int:
    return int(duration_min.to_integral_value(rounding=ROUND_HALF_UP))


async def _fare_for_route(
    db: AsyncSession,
    ride_type_slug: str,
    distance_km: Decimal,
    duration_min: Decimal,
) -> tuple[Decimal, Decimal, str]:
    ride_type = await fare_service.get_ride_type_by_slug(db, ride_type_slug)
    rule = await fare_service.get_fare_rule(db, ride_type.id)
    surge = Decimal("1.00")
    estimated = fare_service.calculate_fare(rule, distance_km, duration_min, surge)
    return estimated, surge, rule.currency


async def estimate_ride(
    db: AsyncSession,
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    drop_lat: Decimal,
    drop_lng: Decimal,
    ride_type_slug: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str]:
    route = await geo_service.get_route(pickup_lat, pickup_lng, drop_lat, drop_lng)
    estimated, surge, currency = await _fare_for_route(
        db, ride_type_slug, route.distance_km, route.duration_min
    )
    return route.distance_km, route.duration_min, estimated, surge, currency


async def quote_ride(
    db: AsyncSession,
    pickup_lat: Decimal,
    pickup_lng: Decimal,
    drop_lat: Decimal,
    drop_lng: Decimal,
) -> RideQuoteResponse:
    route_task = geo_service.get_route(pickup_lat, pickup_lng, drop_lat, drop_lng)
    pickup_addr_task = geo_service.reverse_geocode(pickup_lat, pickup_lng)
    drop_addr_task = geo_service.reverse_geocode(drop_lat, drop_lng)
    route, pickup_address, drop_address = await asyncio.gather(
        route_task, pickup_addr_task, drop_addr_task
    )

    result = await db.execute(select(RideType).where(RideType.is_active.is_(True)))
    ride_types = result.scalars().all()
    trip_min = _trip_duration_min(route.duration_min)
    surge = Decimal("1.00")
    currency = get_settings().default_currency
    options: list[RideQuoteOption] = []

    for ride_type in ride_types:
        rule = await fare_service.get_fare_rule(db, ride_type.id)
        currency = rule.currency
        estimated = fare_service.calculate_fare(
            rule, route.distance_km, route.duration_min, surge
        )
        supply = await supply_service.mock_availability(
            db, pickup_lat, pickup_lng, ride_type_slug=ride_type.slug
        )
        total_eta = (
            (supply.pickup_eta_min + trip_min) if supply.available and supply.pickup_eta_min else None
        )
        options.append(
            RideQuoteOption(
                slug=ride_type.slug,
                name=ride_type.name,
                description=ride_type.description,
                icon_url=ride_type.icon_url,
                available=supply.available,
                drivers_nearby=supply.drivers_nearby,
                estimated_fare=estimated,
                pickup_eta_min=supply.pickup_eta_min if supply.available else None,
                trip_duration_min=trip_min,
                total_eta_min=total_eta,
            )
        )

    options.sort(key=lambda o: (not o.available, o.total_eta_min or 9999))

    return RideQuoteResponse(
        pickup_address=pickup_address,
        drop_address=drop_address,
        route=RouteSummary(
            distance_km=route.distance_km,
            duration_min=route.duration_min,
            polyline=route.polyline,
        ),
        currency=currency,
        surge_multiplier=surge,
        quote_expires_at=datetime.now(timezone.utc) + timedelta(minutes=QUOTE_TTL_MINUTES),
        options=options,
    )


async def rider_owns_ride(db: AsyncSession, rider_id: UUID, ride_id: UUID) -> bool:
    result = await db.execute(
        select(Ride.id).where(Ride.id == ride_id, Ride.rider_id == rider_id)
    )
    return result.scalar_one_or_none() is not None


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
    route = await geo_service.get_route(
        body.pickup.lat, body.pickup.lng, body.drop.lat, body.drop.lng
    )
    estimated, surge, _ = await _fare_for_route(
        db, body.ride_type_slug, route.distance_km, route.duration_min
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
        distance_km=route.distance_km,
        duration_min=route.duration_min,
        route_polyline=route.polyline,
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
    driver = await ride_live_service.driver_summary_for_ride(db, ride)
    leg_polyline = await get_cached_leg_polyline(str(ride.id)) if ride.driver_id else None
    return RideStatusResponse(
        id=ride.id,
        status=ride.status.value,
        message=message,
        driver=driver,
        route_polyline=ride.route_polyline,
        leg_polyline=leg_polyline,
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
    settings = get_settings()
    if ride.status != RideStatus.completed or ride.final_fare is None:
        return InvoiceResponse(available=False)
    driver = await ride_live_service.driver_summary_for_ride(db, ride)
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


async def _record_status(
    db: AsyncSession, ride: Ride, status: RideStatus, message: str | None = None
) -> RideStatusEvent:
    event = RideStatusEvent(ride_id=ride.id, status=status, message=message)
    db.add(event)
    await db.flush()
    payload = await ride_live_service.build_status_payload(
        db, ride, status, message, event.created_at
    )
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
        # Generate OTP now so driver can show it to the rider before the trip starts
        ride.start_otp = f"{secrets.randbelow(1_000_000):06d}"
    elif status == RideStatus.in_progress:
        ride.started_at = now
    elif status == RideStatus.completed:
        ride.completed_at = now
        ride.final_fare = ride.estimated_fare
    elif status == RideStatus.cancelled:
        ride.cancelled_at = now
    await _record_status(db, ride, status, message)


async def _to_ride_response(db: AsyncSession, ride: Ride) -> RideResponse:
    slug = ride.ride_type.slug if ride.ride_type else None
    driver = await ride_live_service.driver_summary_for_ride(db, ride)
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
        route_polyline=ride.route_polyline,
        invoice_available=_invoice_available(ride),
    )
