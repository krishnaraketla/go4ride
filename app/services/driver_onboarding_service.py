"""Shared driver onboarding helpers."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentType, KycStatus, OnboardingStatus
from app.schemas.driver import OnboardingState

REQUIRED_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.license,
    DocumentType.registration,
    DocumentType.insurance,
    DocumentType.profile_photo,
)

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


def step2_complete(profile: DriverProfile, uploaded_types: set[str]) -> bool:
    return (
        documents_complete(uploaded_types)
        and vehicle_details_complete(profile)
        and profile.city_id is not None
        and vehicle_photos_complete(profile)
    )


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


def build_onboarding_state(profile: DriverProfile) -> OnboardingState:
    return OnboardingState(
        onboarding_status=profile.onboarding_status,
        profile_status=profile_status_for(profile),
        application_id=profile.application_id,
        kyc_rejection_reason=profile.kyc_rejection_reason,
        face_verification_completed=profile.face_verification_completed,
        estimated_review_time=estimated_review_time_for(profile),
    )
