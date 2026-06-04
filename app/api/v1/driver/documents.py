"""Driver KYC / document upload endpoints.

Uses S3 presigned PUT URLs so the driver app uploads directly to S3.
The `confirm` endpoint records the file_key after the client finishes the upload.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_driver
from app.db.session import get_db
from app.models.driver import DriverDocument, DriverProfile
from app.models.enums import DocumentStatus
from app.models.user import User
from app.schemas.driver import (
    ConfirmDocumentUploadRequest,
    DocumentResponse,
    DocumentUploadUrlRequest,
    DocumentUploadUrlResponse,
    KycStatusResponse,
)

router = APIRouter(prefix="/documents", tags=["Driver Documents"])


@router.post("/upload-url", response_model=DocumentUploadUrlResponse)
async def get_upload_url(
    body: DocumentUploadUrlRequest,
    driver: Annotated[User, Depends(get_current_driver)],
):
    """Return a presigned S3 PUT URL the client uses to upload the document."""
    settings = get_settings()
    file_key = f"drivers/{driver.id}/{body.document_type.value}/{secrets.token_hex(16)}"

    # If S3 is configured, generate a real presigned URL.
    # Falling back to a placeholder so the app runs without AWS credentials.
    try:
        import boto3  # type: ignore[import]
        from botocore.exceptions import NoCredentialsError  # type: ignore[import]

        s3 = boto3.client("s3", region_name=getattr(settings, "aws_region", "ap-south-1"))
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": getattr(settings, "s3_bucket", "go4ride-kyc"),
                "Key": file_key,
                "ContentType": body.content_type,
            },
            ExpiresIn=900,
        )
    except Exception:
        # In dev without AWS credentials, return a fake URL.
        upload_url = f"https://s3.example.com/{file_key}?presigned=dev"

    return DocumentUploadUrlResponse(upload_url=upload_url, file_key=file_key, expires_in=900)


@router.post("/confirm", response_model=DocumentResponse, status_code=201)
async def confirm_upload(
    body: ConfirmDocumentUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    """After uploading to S3, call this to record the document in the DB."""
    # Upsert: replace any previous pending document of the same type
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
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/kyc-status", response_model=KycStatusResponse)
async def get_kyc_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    driver: Annotated[User, Depends(get_current_driver)],
):
    from app.models.enums import KycStatus
    from app.schemas.driver import DocumentStatusItem, OverallProgress

    profile_result = await db.execute(
        select(DriverProfile).where(DriverProfile.user_id == driver.id)
    )
    profile = profile_result.scalar_one_or_none()
    kyc_status = profile.kyc_status if profile else KycStatus.pending

    # Fetch uploaded documents keyed by type
    docs_result = await db.execute(
        select(DriverDocument).where(DriverDocument.driver_user_id == driver.id)
    )
    uploaded = {d.document_type.value: d for d in docs_result.scalars().all()}

    # Define all required document types with metadata
    required_docs = [
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

    document_items = []
    uploaded_count = 0
    for doc_def in required_docs:
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

    total = len(required_docs)
    percentage = int((uploaded_count / total) * 100)

    return KycStatusResponse(
        success=True,
        kyc_status=kyc_status,
        overall_progress=OverallProgress(
            uploaded=uploaded_count,
            total=total,
            percentage=percentage,
        ),
        documents=document_items,
    )
