"""Driver KYC / document upload endpoints.

Uses S3 presigned PUT URLs so the driver app uploads directly to S3.
The `confirm` endpoint records the file_key after the client finishes the upload.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentStatus, KycStatus
from app.models.user import User
from app.schemas.driver import (
    ConfirmDocumentUploadRequest,
    DocumentResponse,
    DocumentStatusItem,
    DocumentUploadUrlRequest,
    DocumentUploadUrlResponse,
    KycStatusResponse,
    OverallProgress,
)
from app.schemas.response import ApiResponse, ok
from app.services.driver_onboarding_service import (
    REQUIRED_DOC_DEFS,
    get_uploaded_document_types,
    maybe_advance_to_step2,
)
from app.services.s3_service import presigned_put_url

router = APIRouter(prefix="/documents", tags=["Driver Documents"])


@router.post("/upload-url", response_model=ApiResponse[DocumentUploadUrlResponse])
async def get_upload_url(
    body: DocumentUploadUrlRequest,
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Return a presigned S3 PUT URL the client uses to upload the document."""
    file_key = f"drivers/{driver.id}/{body.document_type.value}/{secrets.token_hex(16)}"
    upload_url = presigned_put_url(file_key, body.content_type)

    return ok(
        DocumentUploadUrlResponse(upload_url=upload_url, file_key=file_key, expires_in=900),
        message="Upload URL generated",
    )


@router.post("/confirm", response_model=ApiResponse[DocumentResponse], status_code=201)
async def confirm_upload(
    body: ConfirmDocumentUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """After uploading to S3, call this to record the document in the DB."""
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        from app.core.exceptions import not_found
        raise not_found("Driver profile not found", "PROFILE_NOT_FOUND")

    existing = await db.execute(
        select(DriverDocument).where(
            DriverDocument.driver_user_id == driver.id,
            DriverDocument.document_type == body.document_type,
            DriverDocument.status == DocumentStatus.pending,
        )
    )
    doc = existing.scalar_one_or_none()
    if doc:
        doc.file_key = body.file_key
    else:
        doc = DriverDocument(
            driver_user_id=driver.id,
            document_type=body.document_type,
            file_key=body.file_key,
            status=DocumentStatus.pending,
        )
        db.add(doc)

    uploaded_types = await get_uploaded_document_types(db, driver.id)
    uploaded_types.add(body.document_type.value)
    await maybe_advance_to_step2(db, profile, uploaded_types)

    await db.commit()
    await db.refresh(doc)
    return ok(DocumentResponse.model_validate(doc), message="Document confirmed")


@router.get("/kyc-status", response_model=ApiResponse[KycStatusResponse])
async def get_kyc_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    profile = profile_result.scalar_one_or_none()
    kyc_status = profile.kyc_status if profile else KycStatus.pending

    docs_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_user_id == driver.id)
    )
    uploaded = {d.document_type.value: d for d in docs_result.scalars().all()}

    document_items = []
    uploaded_count = 0
    for doc_def in REQUIRED_DOC_DEFS:
        doc = uploaded.get(doc_def["type"])
        if doc:
            uploaded_count += 1
            status = doc.status.value
            uploaded_at = doc.created_at
            rejection_reason = doc.rejection_reason
        else:
            status = "not_uploaded"
            uploaded_at = None
            rejection_reason = None

        document_items.append(
            DocumentStatusItem(
                type=doc_def["type"],
                label=doc_def["label"],
                description=doc_def["description"],
                status=status,
                sides_required=doc_def["sides_required"],
                uploaded_at=uploaded_at,
                rejection_reason=rejection_reason,
            )
        )

    total = len(REQUIRED_DOC_DEFS)
    percentage = int((uploaded_count / total) * 100)

    return ok(
        KycStatusResponse(
            kyc_status=kyc_status,
            overall_progress=OverallProgress(
                uploaded=uploaded_count,
                total=total,
                percentage=percentage,
            ),
            documents=document_items,
        ),
        message="KYC status retrieved",
    )
