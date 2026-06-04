"""Driver onboarding endpoints — vehicle details and application submission."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import KycStatus, OnboardingStatus
from app.models.user import User
from app.schemas.driver import (
    SubmitApplicationResponse,
    VerificationProgress,
    VehiclePhotos,
    VehicleResponse,
    VehicleSubmitRequest,
    VehicleSubmitResponse,
)

router = APIRouter(prefix="/onboarding", tags=["Driver Onboarding"])


@router.post("/vehicle", response_model=VehicleSubmitResponse, status_code=201)
async def submit_vehicle(
    body: VehicleSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Submit vehicle details during onboarding (Screen 5)."""
    profile = await _get_profile_or_404(db, driver.id)

    # Update profile with vehicle details
    profile.vehicle_type = body.vehicle_type
    profile.vehicle_make = body.make
    profile.vehicle_model = body.model
    profile.vehicle_year = body.year
    profile.vehicle_plate = body.plate_number
    profile.vehicle_color = body.color

    # Advance onboarding status if still at pending/documents stage
    if profile.onboarding_status in (
        OnboardingStatus.pending,
        OnboardingStatus.documents_uploaded,
    ):
        profile.onboarding_status = OnboardingStatus.vehicle_submitted

    await db.commit()

    vehicle_id = f"veh_{str(driver.id)[:8]}"
    return VehicleSubmitResponse(
        success=True,
        vehicle=VehicleResponse(
            vehicle_id=vehicle_id,
            driver_id=str(driver.id),
            type=body.vehicle_type.value,
            make=body.make,
            model=body.model,
            year=body.year,
            plate_number=body.plate_number,
            color=body.color,
            photos=VehiclePhotos(),       # photos handled separately via documents upload
            status="pending_review",
        ),
        onboarding_step="submit_application",
    )


@router.post("/submit", response_model=SubmitApplicationResponse)
async def submit_application(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Submit the driver application for review (Screen 7)."""
    profile = await _get_profile_or_404(db, driver.id)

    # Check what has been completed
    docs_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_user_id == driver.id)
    )
    docs = docs_result.scalars().all()
    documents_uploaded = len(docs) > 0
    vehicle_submitted = profile.vehicle_make is not None and profile.vehicle_plate is not None

    # Collect missing steps
    missing = []
    if not documents_uploaded:
        missing.append("documents_uploaded")
    if not vehicle_submitted:
        missing.append("vehicle_details_submitted")

    if missing:
        raise bad_request(
            f"Onboarding incomplete. Missing steps: {', '.join(missing)}",
            "ONBOARDING_INCOMPLETE",
        )

    # Advance status to under_review
    profile.onboarding_status = OnboardingStatus.under_review
    profile.kyc_status = KycStatus.submitted
    submitted_at = datetime.now(timezone.utc)
    await db.commit()

    application_id = f"app_{submitted_at.strftime('%Y')}_{str(driver.id)[:6].upper()}"

    return SubmitApplicationResponse(
        success=True,
        application_id=application_id,
        onboarding_status="under_review",
        verification_progress=VerificationProgress(
            documents_uploaded=documents_uploaded,
            vehicle_details_submitted=vehicle_submitted,
            face_verification_completed=False,
        ),
        estimated_review_time="24 hours",
        submitted_at=submitted_at,
        message="Your application is under review. You will be notified once approved.",
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_profile_or_404(db: AsyncSession, driver_id) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found(
            "Driver profile not found. Create your profile first.",
            "PROFILE_NOT_FOUND",
        )
    return profile
