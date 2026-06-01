from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.enums import KycStatus
from app.models.ride import RideType
from app.models.user import User
from app.schemas.driver import (
    DriverEarningsResponse,
    DriverProfileResponse,
    DriverStatsResponse,
    UpdateDriverProfileRequest,
)

router = APIRouter(prefix="/profile", tags=["Driver Profile"])


@router.get("", response_model=DriverProfileResponse)
async def get_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)
    return _to_response(driver, profile)


@router.patch("", response_model=DriverProfileResponse)
async def update_profile(
    body: UpdateDriverProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)

    if body.name is not None:
        driver.name = body.name
    if body.vehicle_model is not None:
        profile.vehicle_model = body.vehicle_model
    if body.vehicle_plate is not None:
        profile.vehicle_plate = body.vehicle_plate
    if body.vehicle_color is not None:
        profile.vehicle_color = body.vehicle_color

    if body.ride_type_slug is not None:
        rt_result = await db.execute(
            select(RideType).where(RideType.slug == body.ride_type_slug)
        )
        ride_type = rt_result.scalar_one_or_none()
        if ride_type is None:
            raise not_found("Ride type not found", "RIDE_TYPE_NOT_FOUND")
        profile.ride_type_id = ride_type.id

    await db.commit()
    await db.refresh(profile)
    return _to_response(driver, profile)


@router.post("", response_model=DriverProfileResponse, status_code=201)
async def create_profile(
    body: UpdateDriverProfileRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Called during driver onboarding to create the profile for the first time."""
    existing = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise bad_request("Profile already exists", "PROFILE_EXISTS")

    if not body.vehicle_model or not body.vehicle_plate or not body.vehicle_color:
        raise bad_request(
            "vehicle_model, vehicle_plate and vehicle_color are required",
            "MISSING_FIELDS",
        )

    ride_type_id = None
    if body.ride_type_slug:
        rt_result = await db.execute(
            select(RideType).where(RideType.slug == body.ride_type_slug)
        )
        ride_type = rt_result.scalar_one_or_none()
        if ride_type is None:
            raise not_found("Ride type not found", "RIDE_TYPE_NOT_FOUND")
        ride_type_id = ride_type.id

    profile = DriverProfile(
        user_id=driver.id,
        vehicle_model=body.vehicle_model,
        vehicle_plate=body.vehicle_plate,
        vehicle_color=body.vehicle_color,
        ride_type_id=ride_type_id,
        kyc_status=KycStatus.pending,
    )
    db.add(profile)
    if body.name:
        driver.name = body.name
    await db.commit()
    await db.refresh(profile)
    return _to_response(driver, profile)


@router.get("/stats", response_model=DriverStatsResponse)
async def get_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_or_404(db, driver.id)
    return DriverStatsResponse(
        total_rides=profile.total_rides or 0,
        completed_rides=profile.total_rides or 0,
        cancelled_rides=0,
        acceptance_rate=1.0,
        rating=profile.rating,
    )


@router.get("/earnings", response_model=DriverEarningsResponse)
async def get_earnings(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    # TODO: aggregate from ride final_fare in a real implementation
    return DriverEarningsResponse(
        today=Decimal("0.00"),
        this_week=Decimal("0.00"),
        this_month=Decimal("0.00"),
        total=Decimal("0.00"),
        currency="INR",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_404(db: AsyncSession, driver_id) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile)
        .where(DriverProfile.user_id == driver_id)
        .options(selectinload(DriverProfile.ride_type))
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found("Driver profile not found. Complete onboarding first.", "PROFILE_NOT_FOUND")
    return profile


def _to_response(driver: User, profile: DriverProfile) -> DriverProfileResponse:
    return DriverProfileResponse(
        driver_id=driver.id,
        name=driver.name,
        phone=driver.phone,
        vehicle_model=profile.vehicle_model,
        vehicle_plate=profile.vehicle_plate,
        vehicle_color=profile.vehicle_color,
        ride_type_slug=profile.ride_type.slug if profile.ride_type else None,
        driver_status=profile.driver_status,
        kyc_status=profile.kyc_status,
        rating=profile.rating,
        total_rides=profile.total_rides or 0,
    )
