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
    RideRatingResponse,
    StartRideRequest,
    SubmitRideRatingRequest,
)
from app.schemas.response import ApiResponse, ok
from app.services import driver_ride_service, ride_rating_service

router = APIRouter(prefix="/rides", tags=["Driver Rides"])


@router.get("/search", response_model=ApiResponse[DriverRideSearchResponse])
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
    data = await driver_ride_service.search_nearby_rides(
        db, driver, lat, lng, effective_radius, limit
    )
    return ok(data, message="Rides found")


@router.get("/pending", response_model=ApiResponse[DriverRideResponse | None], deprecated=True)
async def get_pending_ride(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Deprecated: use GET /rides/search. Returns the nearest open ride within default radius."""
    data = await driver_ride_service.get_pending_ride(db, driver)
    message = "Pending ride retrieved" if data else "No pending ride"
    return ok(data, message=message)


@router.get("/current", response_model=ApiResponse[DriverRideResponse | None])
async def get_current_ride(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Get the driver's active ride (assigned / arrived / in_progress)."""
    data = await driver_ride_service.get_current_ride(db, driver)
    message = "Active ride retrieved" if data else "No active ride"
    return ok(data, message=message)


@router.post("/{ride_id}/accept", response_model=ApiResponse[AcceptRideResponse])
async def accept_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    ride = await driver_ride_service.accept_ride(db, driver, ride_id)
    await db.commit()
    return ok(
        AcceptRideResponse(
            ride_id=ride.id,
            status=ride.status,
            message="Ride accepted. Head to pickup location.",
        ),
        message="Ride accepted",
    )


@router.post("/{ride_id}/reject", response_model=ApiResponse[RejectRideResponse])
async def reject_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    result = await driver_ride_service.reject_ride(db, driver, ride_id)
    await db.commit()
    return ok(RejectRideResponse(**result), message="Ride rejected")


@router.post("/{ride_id}/arrived", response_model=ApiResponse[DriverRideResponse])
async def arrived_at_pickup(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Driver has arrived at the pickup location. OTP is generated here."""
    ride = await driver_ride_service.arrived_at_pickup(db, driver, ride_id)
    await db.commit()
    return ok(ride, message="Arrived at pickup")


@router.post("/{ride_id}/start", response_model=ApiResponse[DriverRideResponse])
async def start_ride(
    ride_id: UUID,
    body: StartRideRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Driver verifies the rider's OTP and starts the ride."""
    ride = await driver_ride_service.start_ride(db, driver, ride_id, body.otp)
    await db.commit()
    return ok(ride, message="Ride started")


@router.post("/{ride_id}/complete", response_model=ApiResponse[CompleteRideResponse])
async def complete_ride(
    ride_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    ride = await driver_ride_service.complete_ride(db, driver, ride_id)
    await db.commit()
    return ok(
        CompleteRideResponse(
            ride_id=ride.id,
            status=ride.status,
            final_fare=ride.final_fare,
            message="Ride completed successfully.",
        ),
        message="Ride completed",
    )


@router.get("/history", response_model=ApiResponse[DriverRideHistoryResponse])
async def ride_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: str = Query(
        "terminal",
        description="terminal (default), all, completed, or cancelled",
    ),
):
    rides, total = await driver_ride_service.get_driver_ride_history(
        db, driver, page, limit, status
    )
    return ok(
        DriverRideHistoryResponse(rides=rides, total=total, page=page, limit=limit),
        message="Ride history retrieved",
    )


@router.post("/{ride_id}/rate", response_model=ApiResponse[RideRatingResponse])
async def rate_rider(
    ride_id: UUID,
    body: SubmitRideRatingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    ride = await ride_rating_service.get_ride_for_rating(db, ride_id, driver)
    rating = await ride_rating_service.submit_rating(
        db, ride, driver, body.score, body.comment
    )
    await db.commit()
    return ok(
        RideRatingResponse(
            ride_id=str(ride_id),
            score=rating.score,
            message="Rating submitted",
        ),
        message="Rating submitted",
    )
