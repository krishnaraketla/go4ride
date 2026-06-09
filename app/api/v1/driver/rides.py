from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.user import User
from app.schemas.driver import (
    AcceptRideResponse,
    CompleteRideResponse,
    DriverRideHistoryResponse,
    DriverRideResponse,
    DriverRideSearchResponse,
    RejectRideResponse,
    StartRideRequest,
)
from app.services import driver_ride_service

router = APIRouter(prefix="/rides", tags=["Driver Rides"])


@router.get("/search", response_model=DriverRideSearchResponse)
async def search_rides(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    lat: Decimal = Query(..., ge=-90, le=90),
    lng: Decimal = Query(..., ge=-180, le=180),
    radius_km: float | None = Query(default=None, ge=0.5, le=50),
    limit: int = Query(default=10, ge=1, le=20),
):
    """Search for open rides near the driver's current location."""
    settings = get_settings()
    effective_radius = radius_km if radius_km is not None else settings.driver_search_default_radius_km
    if effective_radius > settings.driver_search_max_radius_km:
        effective_radius = settings.driver_search_max_radius_km
    return await driver_ride_service.search_nearby_rides(
        db, driver, lat, lng, effective_radius, limit
    )


@router.get("/pending", response_model=DriverRideResponse | None, deprecated=True)
async def get_pending_ride(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Deprecated: use GET /rides/search. Returns the nearest open ride within default radius."""
    return await driver_ride_service.get_pending_ride(db, driver)


@router.get("/current", response_model=DriverRideResponse | None)
async def get_current_ride(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Get the driver's active ride (assigned / arrived / in_progress)."""
    return await driver_ride_service.get_current_ride(db, driver)


@router.post("/{ride_id}/accept", response_model=AcceptRideResponse)
async def accept_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    ride = await driver_ride_service.accept_ride(db, driver, ride_id)
    await db.commit()
    return AcceptRideResponse(
        ride_id=ride.id,
        status=ride.status,
        message="Ride accepted. Head to pickup location.",
    )


@router.post("/{ride_id}/reject", response_model=RejectRideResponse)
async def reject_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    result = await driver_ride_service.reject_ride(db, driver, ride_id)
    await db.commit()
    return RejectRideResponse(**result)


@router.post("/{ride_id}/arrived", response_model=DriverRideResponse)
async def arrived_at_pickup(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Driver has arrived at the pickup location. OTP is generated here."""
    ride = await driver_ride_service.arrived_at_pickup(db, driver, ride_id)
    await db.commit()
    return ride


@router.post("/{ride_id}/start", response_model=DriverRideResponse)
async def start_ride(
    ride_id: UUID,
    body: StartRideRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Driver verifies the rider's OTP and starts the ride."""
    ride = await driver_ride_service.start_ride(db, driver, ride_id, body.otp)
    await db.commit()
    return ride


@router.post("/{ride_id}/complete", response_model=CompleteRideResponse)
async def complete_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    ride = await driver_ride_service.complete_ride(db, driver, ride_id)
    await db.commit()
    return CompleteRideResponse(
        ride_id=ride.id,
        status=ride.status,
        final_fare=ride.final_fare,
        message="Ride completed successfully.",
    )


@router.get("/history", response_model=DriverRideHistoryResponse)
async def ride_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    rides, total = await driver_ride_service.get_driver_ride_history(db, driver, page, limit)
    return DriverRideHistoryResponse(rides=rides, total=total, page=page, limit=limit)
