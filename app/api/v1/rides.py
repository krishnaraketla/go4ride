from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db, get_idempotency_key
from app.models.ride import RideType
from app.models.user import User
from app.schemas.invoice import InvoiceResponse
from app.schemas.response import ApiResponse, ok
from app.schemas.ride import (
    CreateRideRequest,
    RideEstimateRequest,
    RideEstimateResponse,
    RepeatRideResponse,
    RideHistoryResponse,
    RideResponse,
    RideStatusResponse,
    RideTypeResponse,
)
from app.services import ride_service

router = APIRouter(tags=["rides"])


@router.get("/ride-types", response_model=ApiResponse[list[RideTypeResponse]])
async def list_ride_types(db: Annotated[AsyncSession, Depends(get_db)]):
    """List active ride types (mini, sedan, bike, xl)."""

    result = await db.execute(select(RideType).where(RideType.is_active.is_(True)))
    return ok(result.scalars().all(), message="Ride types retrieved")


@router.post("/rides/estimate", response_model=ApiResponse[RideEstimateResponse])
async def estimate_ride(body: RideEstimateRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Get distance, duration, and fare quote for a route."""

    distance_km, duration_min, estimated, surge, currency = await ride_service.estimate_ride(
        db, body.pickup.lat, body.pickup.lng, body.drop.lat, body.drop.lng, body.ride_type_slug
    )
    return ok(
        RideEstimateResponse(
            distance_km=distance_km,
            duration_min=duration_min,
            estimated_fare=estimated,
            currency=currency,
            surge_multiplier=surge,
        ),
        message="Fare estimate calculated",
    )


@router.post("/rides", response_model=ApiResponse[RideResponse])
async def create_ride(
    body: CreateRideRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)] = None,
):
    """Book a ride. Optional `Idempotency-Key` header prevents duplicate bookings."""

    ride = await ride_service.create_ride(db, rider, body, idempotency_key)
    return ok(ride, message="Ride booked")


@router.get("/rides/history", response_model=ApiResponse[RideHistoryResponse])
async def ride_history(
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query(
        "terminal",
        description="terminal (default), all, completed, or cancelled",
    ),
):
    """Paginated ride history for the Bookings screen."""

    items, total = await ride_service.get_ride_history(db, rider, page, limit, status)
    return ok(
        RideHistoryResponse(items=items, page=page, limit=limit, total=total),
        message="Ride history retrieved",
    )


@router.post("/rides/{ride_id}/repeat", response_model=ApiResponse[RepeatRideResponse])
async def repeat_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return estimate + create payload to re-book a past ride."""

    payload = await ride_service.get_repeat_ride_payload(db, rider, ride_id)
    return ok(payload, message="Repeat ride payload retrieved")


@router.post("/rides/{ride_id}/cancel", response_model=ApiResponse[RideResponse])
async def cancel_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Cancel an active ride owned by the current rider."""

    ride = await ride_service.cancel_ride(db, rider, ride_id)
    return ok(ride, message="Ride cancelled")


@router.get("/rides/{ride_id}/status", response_model=ApiResponse[RideStatusResponse])
async def ride_status(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Lightweight status poll (prefer WebSocket for live updates)."""

    status = await ride_service.get_ride_status(db, rider, ride_id)
    return ok(status, message="Ride status retrieved")


@router.get("/rides/{ride_id}", response_model=ApiResponse[RideResponse])
async def get_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Full ride details including driver info when assigned."""

    ride = await ride_service.get_ride(db, rider, ride_id)
    return ok(ride, message="Ride retrieved")


@router.get("/rides/{ride_id}/invoice", response_model=ApiResponse[InvoiceResponse])
async def ride_invoice(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Receipt / invoice stub for completed rides."""

    invoice = await ride_service.get_ride_invoice(db, rider, ride_id)
    return ok(invoice, message="Invoice retrieved")
