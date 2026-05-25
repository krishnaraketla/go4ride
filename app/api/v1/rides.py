from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_rider, get_db, get_idempotency_key
from app.models.ride import RideType
from app.models.user import User
from app.schemas.invoice import InvoiceResponse
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


@router.get("/ride-types", response_model=list[RideTypeResponse])
async def list_ride_types(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(RideType).where(RideType.is_active.is_(True)))
    return result.scalars().all()


@router.post("/rides/estimate", response_model=RideEstimateResponse)
async def estimate_ride(body: RideEstimateRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    distance_km, duration_min, estimated, surge, currency = await ride_service.estimate_ride(
        db, body.pickup.lat, body.pickup.lng, body.drop.lat, body.drop.lng, body.ride_type_slug
    )
    return RideEstimateResponse(
        distance_km=distance_km,
        duration_min=duration_min,
        estimated_fare=estimated,
        currency=currency,
        surge_multiplier=surge,
    )


@router.post("/rides", response_model=RideResponse)
async def create_ride(
    body: CreateRideRequest,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)] = None,
):
    return await ride_service.create_ride(db, rider, body, idempotency_key)


@router.get("/rides/history", response_model=RideHistoryResponse)
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
    items, total = await ride_service.get_ride_history(db, rider, page, limit, status)
    return RideHistoryResponse(items=items, page=page, limit=limit, total=total)


@router.post("/rides/{ride_id}/repeat", response_model=RepeatRideResponse)
async def repeat_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ride_service.get_repeat_ride_payload(db, rider, ride_id)


@router.post("/rides/{ride_id}/cancel", response_model=RideResponse)
async def cancel_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ride_service.cancel_ride(db, rider, ride_id)


@router.get("/rides/{ride_id}/status", response_model=RideStatusResponse)
async def ride_status(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ride_service.get_ride_status(db, rider, ride_id)


@router.get("/rides/{ride_id}", response_model=RideResponse)
async def get_ride(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ride_service.get_ride(db, rider, ride_id)


@router.get("/rides/{ride_id}/invoice", response_model=InvoiceResponse)
async def ride_invoice(
    ride_id: UUID,
    rider: Annotated[User, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ride_service.get_ride_invoice(db, rider, ride_id)
