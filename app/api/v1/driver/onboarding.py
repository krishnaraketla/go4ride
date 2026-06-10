"""Driver onboarding endpoints — multipart document, vehicle, and face verification."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.core.exceptions import bad_request, not_found
from app.db.session import get_db
from app.models.city import City
from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentStatus, DocumentType, KycStatus, OnboardingStatus, VehicleType
from app.models.user import User
from app.schemas.driver import (
    DocumentSummary,
    DocumentsSubmitResponse,
    FaceVerificationResponse,
    VehicleSubmitResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services.driver_onboarding_service import (
    REQUIRED_DOCUMENT_TYPES,
    build_onboarding_state,
    documents_complete,
    generate_application_id,
    get_uploaded_document_types,
    maybe_advance_to_step2,
)
from app.services.driver_upload_service import upload_driver_file

router = APIRouter(prefix="/onboarding", tags=["Driver Onboarding"])

_DOC_FIELD_MAP: dict[str, DocumentType] = {
    "license": DocumentType.license,
    "registration": DocumentType.registration,
    "insurance": DocumentType.insurance,
    "profile_photo": DocumentType.profile_photo,
}


@router.post("/documents", response_model=ApiResponse[DocumentsSubmitResponse], status_code=201)
async def submit_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    license: Annotated[UploadFile, File()],
    registration: Annotated[UploadFile, File()],
    insurance: Annotated[UploadFile, File()],
    profile_photo: Annotated[UploadFile, File()],
):
    """Upload all KYC documents in one request. Advances onboarding to step2."""
    profile = await _get_profile_or_404(db, driver.id)

    if profile.onboarding_status not in (OnboardingStatus.step1, OnboardingStatus.kyc_rejected):
        raise bad_request(
            "Documents can only be submitted during step 1 or after rejection",
            "INVALID_ONBOARDING_STEP",
        )

    uploads = {
        "license": license,
        "registration": registration,
        "insurance": insurance,
        "profile_photo": profile_photo,
    }

    saved_docs: list[DriverDocument] = []
    for field_name, doc_type in _DOC_FIELD_MAP.items():
        file_key = await upload_driver_file(
            driver.id, doc_type.value, uploads[field_name], field_name
        )

        existing = await db.execute(
            select(DriverDocument).where(
                DriverDocument.driver_user_id == driver.id,
                DriverDocument.document_type == doc_type,
            )
        )
        doc = existing.scalar_one_or_none()
        if doc:
            doc.file_key = file_key
            doc.status = DocumentStatus.pending
            doc.rejection_reason = None
        else:
            doc = DriverDocument(
                driver_user_id=driver.id,
                document_type=doc_type,
                file_key=file_key,
                status=DocumentStatus.pending,
            )
            db.add(doc)
        saved_docs.append(doc)

    uploaded_types = {dt.value for dt in REQUIRED_DOCUMENT_TYPES}
    await maybe_advance_to_step2(db, profile, uploaded_types)
    await db.commit()

    for doc in saved_docs:
        await db.refresh(doc)

    return ok(
        DocumentsSubmitResponse(
            onboarding=build_onboarding_state(profile),
            documents=[
                DocumentSummary(
                    type=doc.document_type.value,
                    id=doc.id,
                    status=doc.status,
                    created_at=doc.created_at,
                )
                for doc in saved_docs
            ],
        ),
        message="Documents submitted",
    )


@router.post("/vehicle", response_model=ApiResponse[VehicleSubmitResponse], status_code=201)
async def submit_vehicle(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    vehicle_type: Annotated[str, Form()],
    make: Annotated[str, Form()],
    model: Annotated[str, Form()],
    year: Annotated[int, Form()],
    plate_number: Annotated[str, Form()],
    color: Annotated[str, Form()],
    city_slug: Annotated[str, Form()],
    photo_front: Annotated[UploadFile, File()],
    photo_back: Annotated[UploadFile, File()],
    photo_left: Annotated[UploadFile, File()],
    photo_right: Annotated[UploadFile, File()],
):
    """Submit vehicle details, city, and photos. Auto-submits application for review."""
    profile = await _get_profile_or_404(db, driver.id)

    if profile.onboarding_status not in (OnboardingStatus.step2, OnboardingStatus.kyc_rejected):
        raise bad_request(
            "Complete document upload before submitting vehicle details",
            "INVALID_ONBOARDING_STEP",
        )

    uploaded_types = await get_uploaded_document_types(db, driver.id)
    if not documents_complete(uploaded_types):
        raise bad_request(
            "All required documents must be uploaded first",
            "DOCUMENTS_INCOMPLETE",
        )

    try:
        parsed_vehicle_type = VehicleType(vehicle_type)
    except ValueError:
        raise bad_request(
            "vehicle_type must be auto, taxi, or cab",
            "INVALID_VEHICLE_TYPE",
        ) from None

    if year < 2000 or year > 2030:
        raise bad_request("year must be between 2000 and 2030", "INVALID_YEAR")

    city_result = await db.execute(
        select(City).where(City.slug == city_slug, City.is_active.is_(True))
    )
    city = city_result.scalar_one_or_none()
    if city is None:
        raise not_found("City not found", "CITY_NOT_FOUND")

    photo_keys = {
        "front": await upload_driver_file(driver.id, "vehicle-photos/front", photo_front, "photo_front"),
        "back": await upload_driver_file(driver.id, "vehicle-photos/back", photo_back, "photo_back"),
        "left": await upload_driver_file(driver.id, "vehicle-photos/left", photo_left, "photo_left"),
        "right": await upload_driver_file(driver.id, "vehicle-photos/right", photo_right, "photo_right"),
    }

    profile.vehicle_type = parsed_vehicle_type
    profile.vehicle_make = make
    profile.vehicle_model = model
    profile.vehicle_year = year
    profile.vehicle_plate = plate_number
    profile.vehicle_color = color
    profile.city_id = city.id
    profile.vehicle_photo_front_key = photo_keys["front"]
    profile.vehicle_photo_back_key = photo_keys["back"]
    profile.vehicle_photo_left_key = photo_keys["left"]
    profile.vehicle_photo_right_key = photo_keys["right"]

    if profile.onboarding_status == OnboardingStatus.kyc_rejected:
        profile.kyc_rejection_reason = None
        profile.kyc_status = KycStatus.pending

    submitted_at = datetime.now(timezone.utc)
    profile.onboarding_status = OnboardingStatus.application_submitted
    profile.kyc_status = KycStatus.submitted
    profile.application_id = generate_application_id(driver.id)
    profile.submitted_at = submitted_at

    await db.commit()

    return ok(
        VehicleSubmitResponse(
            onboarding=build_onboarding_state(profile),
            submitted_at=submitted_at,
        ),
        message="Application submitted for review",
    )


@router.post("/face-verification", response_model=ApiResponse[FaceVerificationResponse])
async def submit_face_verification(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    photo: Annotated[UploadFile, File()],
):
    """Upload face verification photo while application is under review."""
    profile = await _get_profile_or_404(db, driver.id)

    if profile.onboarding_status != OnboardingStatus.application_submitted:
        raise bad_request(
            "Face verification is only available while application is under review",
            "INVALID_ONBOARDING_STEP",
        )

    file_key = await upload_driver_file(
        driver.id, "face-verification", photo, "photo"
    )
    profile.face_verification_file_key = file_key
    profile.face_verification_completed = True
    await db.commit()

    return ok(
        FaceVerificationResponse(onboarding=build_onboarding_state(profile)),
        message="Face verification completed",
    )


async def _get_profile_or_404(db: AsyncSession, driver_id) -> DriverProfile:
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
