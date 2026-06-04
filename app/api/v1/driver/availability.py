"""Driver availability / status endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.driver import DriverProfile
from app.models.enums import DriverStatus, KycStatus
from app.models.user import User
from app.schemas.driver import UpdateLocationRequest, UpdateLocationResponse

router = APIRouter(tags=["Driver Availability"])


# ---------------------------------------------------------------------------
# Schemas (inline — specific to this module)
# ---------------------------------------------------------------------------

class DriverStatusRequest(BaseModel):
    status: str = Field(..., examples=["online", "offline"])
    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    heading: float | None = Field(default=None, ge=0, le=360)


class DriverStatusResponse(BaseModel):
    success: bool = True
    driver_id: str
    status: str
    updated_at: datetime
    dispatch_pool: str
    message: str


# ---------------------------------------------------------------------------
# Single PATCH /driver/status endpoint (replaces /online and /offline)
# ---------------------------------------------------------------------------

@router.patch("/driver/status", response_model=DriverStatusResponse)
async def update_driver_status(
    body: DriverStatusRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Go online or offline. Replaces the separate /online and /offline endpoints."""
    if body.status not in ("online", "offline"):
        raise bad_request("status must be 'online' or 'offline'", "INVALID_STATUS")

    profile = await _get_profile_or_404(db, driver.id)

    if body.status == "online":
        if profile.kyc_status != KycStatus.approved:
            raise bad_request(
                "KYC must be approved before going online", "KYC_NOT_APPROVED"
            )
        if profile.driver_status == DriverStatus.on_ride:
            raise bad_request("Cannot change status while on a ride", "ON_RIDE")
        profile.driver_status = DriverStatus.online
        dispatch_pool = "active"
        message = "You are now online and accepting rides"
    else:
        if profile.driver_status == DriverStatus.on_ride:
            raise bad_request("Cannot go offline while on a ride", "ON_RIDE")
        profile.driver_status = DriverStatus.offline
        dispatch_pool = "inactive"
        message = "You are now offline"

    # Always update location when status changes
    profile.current_lat = body.latitude
    profile.current_lng = body.longitude

    updated_at = datetime.now(timezone.utc)
    await db.commit()

    return DriverStatusResponse(
        success=True,
        driver_id=str(driver.id),
        status=body.status,
        updated_at=updated_at,
        dispatch_pool=dispatch_pool,
        message=message,
    )


# ---------------------------------------------------------------------------
# Location update (keep for continuous GPS pings while online)
# ---------------------------------------------------------------------------

@router.patch("/driver/location", response_model=UpdateLocationResponse)
async def update_location(
    body: UpdateLocationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Continuous GPS location update while driver is online."""
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
