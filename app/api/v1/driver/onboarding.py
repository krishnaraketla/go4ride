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
    OnboardingStatusResponse,
    VehicleSubmitResponse,
)
from app.schemas.response import ApiResponse, ok
from app.services.driver_onboarding_service import (
    REQUIRED_DOCUMENT_TYPES,
    build_onboarding_state,
    documents_complete,
    get_uploaded_document_types,
    maybe_advance_to_step2,
    step2_complete,
)
from app.services.driver_upload_service import upload_driver_file

router = APIRouter(prefix="/onboarding", tags=["Driver Onboarding"])

_DOC_FIELD_MAP: dict[str, DocumentType] = {
    "license": DocumentType.license,
    "registration": DocumentType.registration,
    "insurance": DocumentType.insurance,
}


@router.post("/documents", response_model=ApiResponse[DocumentsSubmitResponse], status_code=201)
async def submit_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    license: Annotated[UploadFile, File()],
    registration: Annotated[UploadFile, File()],
    insurance: Annotated[UploadFile, File()],
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


@router.get("/status", response_model=ApiResponse[OnboardingStatusResponse])
async def get_onboarding_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Return current onboarding state for routing."""
    profile = await _get_profile_or_404(db, driver.id)
    return ok(OnboardingStatusResponse(onboarding=build_onboarding_state(profile)))


@router.patch("/vehicle", response_model=ApiResponse[VehicleSubmitResponse])
async def update_vehicle(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
    vehicle_type: Annotated[str | None, Form()] = None,
    make: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    year: Annotated[int | None, Form()] = None,
    plate_number: Annotated[str | None, Form()] = None,
    color: Annotated[str | None, Form()] = None,
    city_slug: Annotated[str | None, Form()] = None,
    photo_front: Annotated[UploadFile | None, File()] = None,
    photo_back: Annotated[UploadFile | None, File()] = None,
    photo_left: Annotated[UploadFile | None, File()] = None,
    photo_right: Annotated[UploadFile | None, File()] = None,
):
    """Save vehicle details, city, and photos incrementally. Auto-submits when complete."""
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

    if not any(
        [
            vehicle_type is not None,
            make is not None,
            model is not None,
            year is not None,
            plate_number is not None,
            color is not None,
            city_slug is not None,
            _is_upload_provided(photo_front),
            _is_upload_provided(photo_back),
            _is_upload_provided(photo_left),
            _is_upload_provided(photo_right),
        ]
    ):
        raise bad_request("At least one field must be provided", "NO_FIELDS")

    if vehicle_type is not None:
        try:
            profile.vehicle_type = VehicleType(vehicle_type)
        except ValueError:
            raise bad_request(
                "vehicle_type must be auto, taxi, or cab",
                "INVALID_VEHICLE_TYPE",
            ) from None

    if make is not None:
        profile.vehicle_make = make
    if model is not None:
        profile.vehicle_model = model
    if year is not None:
        if year < 2000 or year > 2030:
            raise bad_request("year must be between 2000 and 2030", "INVALID_YEAR")
        profile.vehicle_year = year
    if plate_number is not None:
        profile.vehicle_plate = plate_number
    if color is not None:
        profile.vehicle_color = color

    if city_slug is not None:
        city_result = await db.execute(
            select(City).where(City.slug == city_slug, City.is_active.is_(True))
        )
        city = city_result.scalar_one_or_none()
        if city is None:
            raise not_found("City not found", "CITY_NOT_FOUND")
        profile.city_id = city.id

    photo_uploads = {
        "front": (photo_front, "vehicle-photos/front", "photo_front", "vehicle_photo_front_key"),
        "back": (photo_back, "vehicle-photos/back", "photo_back", "vehicle_photo_back_key"),
        "left": (photo_left, "vehicle-photos/left", "photo_left", "vehicle_photo_left_key"),
        "right": (photo_right, "vehicle-photos/right", "photo_right", "vehicle_photo_right_key"),
    }
    for _side, (upload, folder, field_name, attr) in photo_uploads.items():
        if _is_upload_provided(upload):
            file_key = await upload_driver_file(driver.id, folder, upload, field_name)
            setattr(profile, attr, file_key)

    submitted_at: datetime | None = None
    if step2_complete(profile, uploaded_types):
        if profile.onboarding_status == OnboardingStatus.kyc_rejected:
            profile.kyc_rejection_reason = None
            profile.kyc_status = KycStatus.pending

        submitted_at = datetime.now(timezone.utc)
        profile.onboarding_status = OnboardingStatus.application_submitted
        profile.kyc_status = KycStatus.submitted
        profile.submitted_at = submitted_at
        message = "Application submitted for review"
    else:
        message = "Vehicle details saved"

    await db.commit()

    return ok(
        VehicleSubmitResponse(
            onboarding=build_onboarding_state(profile),
            submitted_at=submitted_at,
        ),
        message=message,
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


def _is_upload_provided(file: UploadFile | None) -> bool:
    return file is not None and bool(file.filename)


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
