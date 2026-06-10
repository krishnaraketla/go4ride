"""Shared validation and S3 upload helpers for driver onboarding multipart endpoints."""

import secrets
from uuid import UUID

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import bad_request
from app.services.s3_service import upload_file

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/jpg",
        "application/pdf",
    }
)


async def read_and_validate_upload(file: UploadFile, field_name: str) -> tuple[bytes, str]:
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise bad_request(
            f"{field_name}: unsupported file type '{content_type}'",
            "INVALID_FILE_TYPE",
        )

    body = await file.read()
    if not body:
        raise bad_request(f"{field_name}: file is empty", "EMPTY_FILE")
    if len(body) > max_bytes:
        raise bad_request(
            f"{field_name}: file exceeds {settings.max_upload_size_mb} MB limit",
            "FILE_TOO_LARGE",
        )

    return body, content_type


async def upload_driver_file(
    driver_id: UUID,
    folder: str,
    file: UploadFile,
    field_name: str,
) -> str:
    body, content_type = await read_and_validate_upload(file, field_name)
    file_key = f"drivers/{driver_id}/{folder}/{secrets.token_hex(16)}"
    upload_file(file_key, body, content_type)
    return file_key
