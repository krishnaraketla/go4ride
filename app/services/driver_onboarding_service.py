"""Shared driver onboarding helpers."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentType, KycStatus, OnboardingStatus
from app.schemas.driver import OnboardingStatusResponse, StepProgress

REQUIRED_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.license,
    DocumentType.registration,
    DocumentType.insurance,
    DocumentType.profile_photo,
)

REQUIRED_DOC_DEFS: list[dict] = [
    {
        "type": "license",
        "label": "Driver License",
        "description": "Front & back side of license",
        "sides_required": ["front", "back"],
    },
    {
        "type": "registration",
        "label": "Vehicle Registration",
        "description": "RC Certificate",
        "sides_required": ["front"],
    },
    {
        "type": "insurance",
        "label": "Insurance",
        "description": "Active certificate of insurance",
        "sides_required": ["front"],
    },
    {
        "type": "profile_photo",
        "label": "Profile Photo",
        "description": "Clear front-facing photo",
        "sides_required": ["front"],
    },
]

ESTIMATED_REVIEW_TIME = "15 minutes"


def profile_status_for(profile: DriverProfile) -> bool:
    return profile.onboarding_status == OnboardingStatus.kyc_approved


def estimated_review_time_for(profile: DriverProfile) -> str | None:
    if profile.onboarding_status == OnboardingStatus.application_submitted:
        return ESTIMATED_REVIEW_TIME
    return None


def documents_complete(uploaded_types: set[str]) -> bool:
    return all(doc.value in uploaded_types for doc in REQUIRED_DOCUMENT_TYPES)


def vehicle_photos_complete(profile: DriverProfile) -> bool:
    return all(
        [
            profile.vehicle_photo_front_key,
            profile.vehicle_photo_back_key,
            profile.vehicle_photo_left_key,
            profile.vehicle_photo_right_key,
        ]
    )


def vehicle_details_complete(profile: DriverProfile) -> bool:
    return all(
        [
            profile.vehicle_type,
            profile.vehicle_make,
            profile.vehicle_model,
            profile.vehicle_year,
            profile.vehicle_plate,
            profile.vehicle_color,
        ]
    )


def step_progress_for(profile: DriverProfile, uploaded_types: set[str]) -> dict[str, bool]:
    return {
        "documents_complete": documents_complete(uploaded_types),
        "vehicle_complete": vehicle_details_complete(profile),
        "city_selected": profile.city_id is not None,
        "vehicle_photos_complete": vehicle_photos_complete(profile),
    }


def step2_complete(profile: DriverProfile, uploaded_types: set[str]) -> bool:
    progress = step_progress_for(profile, uploaded_types)
    return all(progress.values())


def generate_application_id(driver_id: UUID) -> str:
    year = datetime.now(timezone.utc).strftime("%Y")
    return f"app_{year}_{str(driver_id)[:6].upper()}"


async def get_uploaded_document_types(
    db: AsyncSession, driver_id: UUID
) -> set[str]:
    docs_result = await db.execute(
        select(DriverDocument.document_type).where(
            DriverDocument.driver_user_id == driver_id
        )
    )
    return {row[0].value for row in docs_result.all()}


async def maybe_advance_to_step2(
    db: AsyncSession, profile: DriverProfile, uploaded_types: set[str]
) -> None:
    if not documents_complete(uploaded_types):
        return
    if profile.onboarding_status not in (OnboardingStatus.step1, OnboardingStatus.kyc_rejected):
        return
    if profile.onboarding_status == OnboardingStatus.kyc_rejected:
        profile.kyc_rejection_reason = None
        profile.kyc_status = KycStatus.pending
    profile.onboarding_status = OnboardingStatus.step2


def build_onboarding_status_response(
    profile: DriverProfile, uploaded_types: set[str]
) -> OnboardingStatusResponse:
    return OnboardingStatusResponse(
        onboarding_status=profile.onboarding_status,
        profile_status=profile_status_for(profile),
        application_id=profile.application_id,
        kyc_rejection_reason=profile.kyc_rejection_reason,
        face_verification_completed=profile.face_verification_completed,
        estimated_review_time=estimated_review_time_for(profile),
        step_progress=StepProgress(**step_progress_for(profile, uploaded_types)),
    )
