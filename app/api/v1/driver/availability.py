from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.enums import DriverStatus, KycStatus
from app.models.user import User
from app.schemas.driver import (
    DriverAvailabilityResponse,
    DriverGoOnlineRequest,
    UpdateLocationRequest,
    UpdateLocationResponse,
)

router = APIRouter(prefix="/availability", tags=["Driver Availability"])


@router.post("/online", response_model=DriverAvailabilityResponse)
async def go_online(
    body: DriverGoOnlineRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_profile_or_404(db, driver.id)
    if profile.kyc_status != KycStatus.approved:
        raise bad_request("KYC must be approved before going online", "KYC_NOT_APPROVED")

    profile.driver_status = DriverStatus.online
    profile.current_lat = body.lat
    profile.current_lng = body.lng
    await db.commit()
    return DriverAvailabilityResponse(driver_status=DriverStatus.online, message="You are now online")


@router.post("/offline", response_model=DriverAvailabilityResponse)
async def go_offline(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_profile_or_404(db, driver.id)
    if profile.driver_status == DriverStatus.on_ride:
        raise bad_request("Cannot go offline while on a ride", "ON_RIDE")

    profile.driver_status = DriverStatus.offline
    await db.commit()
    return DriverAvailabilityResponse(driver_status=DriverStatus.offline, message="You are now offline")


@router.patch("/location", response_model=UpdateLocationResponse)
async def update_location(
    body: UpdateLocationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_profile_or_404(db, driver.id)
    profile.current_lat = body.lat
    profile.current_lng = body.lng
    await db.commit()
    return UpdateLocationResponse(lat=body.lat, lng=body.lng, updated=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_profile_or_404(db: AsyncSession, driver_id) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found("Driver profile not found", "PROFILE_NOT_FOUND")
    return profile
