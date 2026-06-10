"""Driver onboarding endpoints — vehicle details and application submission."""

import secrets
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.city import City
from app.models.driver import DriverProfile
from app.models.enums import KycStatus, OnboardingStatus, VehiclePhotoSide
from app.models.user import User
from app.schemas.driver import (
    DocumentUploadUrlResponse,
    FaceVerificationConfirmRequest,
    FaceVerificationUploadUrlRequest,
    OnboardingStatusResponse,
    SubmitApplicationResponse,
    VehiclePhotoUploadUrlRequest,
    VehiclePhotos,
    VehicleResponse,
    VehicleSubmitRequest,
    VehicleSubmitResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services.driver_onboarding_service import (
    ESTIMATED_REVIEW_TIME,
    build_onboarding_status_response,
    generate_application_id,
    get_uploaded_document_types,
    step2_complete,
)
from app.services.s3_service import presigned_put_url

router = APIRouter(prefix="/onboarding", tags=["Driver Onboarding"])

_VALID_PHOTO_SIDES = {side.value for side in VehiclePhotoSide}


@router.get("/status", response_model=ApiResponse[OnboardingStatusResponse])
async def get_onboarding_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Poll onboarding state for routing (waiting screen, home, etc.)."""
    profile = await _get_profile_or_404(db, driver.id)
    uploaded_types = await get_uploaded_document_types(db, driver.id)
    return ok(
        build_onboarding_status_response(profile, uploaded_types),
        message="Onboarding status retrieved",
    )


@router.post("/vehicle-photos/upload-url", response_model=ApiResponse[DocumentUploadUrlResponse])
async def get_vehicle_photo_upload_url(
    body: VehiclePhotoUploadUrlRequest,
    driver: Annotated[User, Depends(get_current_driver)],
):
    if body.side not in _VALID_PHOTO_SIDES:
        raise bad_request("side must be front, back, left, or right", "INVALID_SIDE")
    file_key = f"drivers/{driver.id}/vehicle-photos/{body.side}/{secrets.token_hex(16)}"
    upload_url = presigned_put_url(file_key, body.content_type)
    return ok(
        DocumentUploadUrlResponse(upload_url=upload_url, file_key=file_key, expires_in=900),
        message="Upload URL generated",
    )


@router.post("/vehicle", response_model=ApiResponse[VehicleSubmitResponse], status_code=201)
async def submit_vehicle(
    body: VehicleSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Submit vehicle details, city, and photos during onboarding step 2."""
    profile = await _get_profile_or_404(db, driver.id)

    if profile.onboarding_status not in (
        OnboardingStatus.step2,
        OnboardingStatus.kyc_rejected,
    ):
        raise bad_request(
            "Complete document upload (step 1) before submitting vehicle details",
            "INVALID_ONBOARDING_STEP",
        )

    city_result = await db.execute(select(City).where(City.id == body.city_id, City.is_active.is_(True)))
    if city_result.scalar_one_or_none() is None:
        raise not_found("City not found", "CITY_NOT_FOUND")

    profile.vehicle_type = body.vehicle_type
    profile.vehicle_make = body.make
    profile.vehicle_model = body.model
    profile.vehicle_year = body.year
    profile.vehicle_plate = body.plate_number
    profile.vehicle_color = body.color
    profile.city_id = body.city_id
    profile.vehicle_photo_front_key = body.photos.front
    profile.vehicle_photo_back_key = body.photos.back
    profile.vehicle_photo_left_key = body.photos.left
    profile.vehicle_photo_right_key = body.photos.right

    if profile.onboarding_status == OnboardingStatus.kyc_rejected:
        profile.onboarding_status = OnboardingStatus.step2
        profile.kyc_rejection_reason = None
        profile.kyc_status = KycStatus.pending

    await db.commit()

    vehicle_id = f"veh_{str(driver.id)[:8]}"
    return ok(
        VehicleSubmitResponse(
            vehicle=VehicleResponse(
                vehicle_id=vehicle_id,
                driver_id=str(driver.id),
                type=body.vehicle_type.value,
                make=body.make,
                model=body.model,
                year=body.year,
                plate_number=body.plate_number,
                color=body.color,
                photos=VehiclePhotos(
                    front=body.photos.front,
                    back=body.photos.back,
                    left=body.photos.left,
                    right=body.photos.right,
                ),
                status="pending_review",
            ),
            onboarding_step="submit_application",
        ),
        message="Vehicle details submitted",
    )


@router.post("/submit", response_model=ApiResponse[SubmitApplicationResponse])
async def submit_application(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Submit the driver application for review."""
    profile = await _get_profile_or_404(db, driver.id)

    if profile.onboarding_status != OnboardingStatus.step2:
        raise bad_request(
            "Application can only be submitted from step 2",
            "INVALID_ONBOARDING_STEP",
        )

    uploaded_types = await get_uploaded_document_types(db, driver.id)
    if not step2_complete(profile, uploaded_types):
        raise bad_request(
            "Onboarding incomplete. Complete documents, vehicle, city, and photos.",
            "ONBOARDING_INCOMPLETE",
        )

    submitted_at = datetime.now(timezone.utc)
    application_id = generate_application_id(driver.id)

    profile.onboarding_status = OnboardingStatus.application_submitted
    profile.kyc_status = KycStatus.submitted
    profile.application_id = application_id
    profile.submitted_at = submitted_at
    await db.commit()

    return ok(
        SubmitApplicationResponse(
            application_id=application_id,
            onboarding_status=OnboardingStatus.application_submitted,
            profile_status=False,
            estimated_review_time=ESTIMATED_REVIEW_TIME,
            submitted_at=submitted_at,
            message="Your application is under review. You will be notified once approved.",
        ),
        message="Application submitted",
    )


@router.post(
    "/face-verification/upload-url",
    response_model=ApiResponse[DocumentUploadUrlResponse],
)
async def get_face_verification_upload_url(
    body: FaceVerificationUploadUrlRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_profile_or_404(db, driver.id)
    if profile.onboarding_status != OnboardingStatus.application_submitted:
        raise bad_request(
            "Face verification is only available while application is under review",
            "INVALID_ONBOARDING_STEP",
        )

    file_key = f"drivers/{driver.id}/face-verification/{secrets.token_hex(16)}"
    upload_url = presigned_put_url(file_key, body.content_type)
    return ok(
        DocumentUploadUrlResponse(upload_url=upload_url, file_key=file_key, expires_in=900),
        message="Upload URL generated",
    )


@router.post("/face-verification/confirm", response_model=ApiResponse[OnboardingStatusResponse])
async def confirm_face_verification(
    body: FaceVerificationConfirmRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile = await _get_profile_or_404(db, driver.id)
    if profile.onboarding_status != OnboardingStatus.application_submitted:
        raise bad_request(
            "Face verification is only available while application is under review",
            "INVALID_ONBOARDING_STEP",
        )

    profile.face_verification_file_key = body.file_key
    profile.face_verification_completed = True
    await db.commit()

    uploaded_types = await get_uploaded_document_types(db, driver.id)
    return ok(
        build_onboarding_status_response(profile, uploaded_types),
        message="Face verification completed",
    )


async def _get_profile_or_404(db: AsyncSession, driver_id: UUID) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found(
            "Driver profile not found.",
            "PROFILE_NOT_FOUND",
        )
    return profile
