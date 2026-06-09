"""Admin operations for driver KYC application review."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import bad_request, not_found
from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentStatus, KycStatus, OnboardingStatus
from app.models.user import User
from app.schemas.admin import (
    AdminDocumentItem,
    DriverApplicationActionResponse,
    DriverApplicationDetailResponse,
    DriverApplicationListItem,
    DriverApplicationListResponse,
)
from app.services.s3_service import presigned_get_url


def _is_reviewable(profile: DriverProfile) -> bool:
    return (
        profile.onboarding_status == OnboardingStatus.under_review
        or profile.kyc_status == KycStatus.submitted
    )


async def list_driver_applications(
    db: AsyncSession,
    *,
    status: OnboardingStatus,
    page: int,
    limit: int,
) -> DriverApplicationListResponse:
    offset = (page - 1) * limit

    count_result = await db.execute(
        select(func.count())
        .select_from(DriverProfile)
        .where(DriverProfile.onboarding_status == status)
    )
    total = count_result.scalar_one()

    doc_stats = (
        select(
            DriverDocument.driver_user_id,
            func.count(DriverDocument.id).label("documents_count"),
            func.max(DriverDocument.created_at).label("submitted_at"),
        )
        .group_by(DriverDocument.driver_user_id)
        .subquery()
    )

    result = await db.execute(
        select(
            DriverProfile,
            User,
            doc_stats.c.documents_count,
            doc_stats.c.submitted_at,
        )
        .join(User, DriverProfile.user_id == User.id)
        .outerjoin(doc_stats, DriverProfile.user_id == doc_stats.c.driver_user_id)
        .where(DriverProfile.onboarding_status == status)
        .order_by(doc_stats.c.submitted_at.desc().nullslast(), DriverProfile.user_id)
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    applications = [
        DriverApplicationListItem(
            driver_id=profile.user_id,
            name=user.name,
            phone=user.phone,
            onboarding_status=profile.onboarding_status,
            kyc_status=profile.kyc_status,
            vehicle_make=profile.vehicle_make,
            vehicle_model=profile.vehicle_model,
            vehicle_plate=profile.vehicle_plate,
            documents_count=documents_count or 0,
            submitted_at=submitted_at,
        )
        for profile, user, documents_count, submitted_at in rows
    ]

    return DriverApplicationListResponse(
        applications=applications,
        total=total,
        page=page,
        limit=limit,
    )


async def get_driver_application(
    db: AsyncSession,
    driver_id: UUID,
) -> DriverApplicationDetailResponse:
    result = await db.execute(
        select(DriverProfile, User)
        .join(User, DriverProfile.user_id == User.id)
        .where(DriverProfile.user_id == driver_id)
        .options(selectinload(DriverProfile.documents))
    )
    row = result.one_or_none()
    if row is None:
        raise not_found("Driver application not found", "NOT_FOUND")

    profile, user = row
    documents = [
        AdminDocumentItem(
            id=doc.id,
            document_type=doc.document_type,
            status=doc.status.value,
            rejection_reason=doc.rejection_reason,
            created_at=doc.created_at,
            view_url=presigned_get_url(doc.file_key),
        )
        for doc in sorted(profile.documents, key=lambda d: d.created_at)
    ]

    return DriverApplicationDetailResponse(
        driver_id=profile.user_id,
        name=user.name,
        phone=user.phone,
        onboarding_status=profile.onboarding_status,
        kyc_status=profile.kyc_status,
        vehicle_type=profile.vehicle_type,
        vehicle_make=profile.vehicle_make,
        vehicle_model=profile.vehicle_model,
        vehicle_year=profile.vehicle_year,
        vehicle_plate=profile.vehicle_plate,
        vehicle_color=profile.vehicle_color,
        documents=documents,
    )


async def approve_driver_application(
    db: AsyncSession,
    driver_id: UUID,
) -> DriverApplicationActionResponse:
    profile = await _get_profile_or_404(db, driver_id)
    if not _is_reviewable(profile):
        raise bad_request(
            "Application is not pending review",
            "INVALID_STATUS",
        )

    profile.onboarding_status = OnboardingStatus.approved
    profile.kyc_status = KycStatus.approved

    docs_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_user_id == driver_id)
    )
    for doc in docs_result.scalars().all():
        doc.status = DocumentStatus.approved
        doc.rejection_reason = None

    await db.commit()
    await db.refresh(profile)

    return DriverApplicationActionResponse(
        driver_id=profile.user_id,
        onboarding_status=profile.onboarding_status,
        kyc_status=profile.kyc_status,
    )


async def reject_driver_application(
    db: AsyncSession,
    driver_id: UUID,
    reason: str,
) -> DriverApplicationActionResponse:
    profile = await _get_profile_or_404(db, driver_id)
    if not _is_reviewable(profile):
        raise bad_request(
            "Application is not pending review",
            "INVALID_STATUS",
        )

    profile.onboarding_status = OnboardingStatus.rejected
    profile.kyc_status = KycStatus.rejected

    docs_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_user_id == driver_id)
    )
    for doc in docs_result.scalars().all():
        if doc.status == DocumentStatus.pending:
            doc.status = DocumentStatus.rejected
            doc.rejection_reason = reason

    await db.commit()
    await db.refresh(profile)

    return DriverApplicationActionResponse(
        driver_id=profile.user_id,
        onboarding_status=profile.onboarding_status,
        kyc_status=profile.kyc_status,
    )


async def _get_profile_or_404(db: AsyncSession, driver_id: UUID) -> DriverProfile:
    result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise not_found("Driver application not found", "NOT_FOUND")
    return profile
