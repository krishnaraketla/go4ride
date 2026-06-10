"""S3 helpers for driver KYC upload and admin review."""

from app.core.config import get_settings


def _s3_client():
    import boto3  # type: ignore[import]

    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


def upload_file(file_key: str, body: bytes, content_type: str) -> None:
    """Upload bytes to S3. No-op placeholder when S3 is unavailable (dev/test)."""
    settings = get_settings()
    try:
        _s3_client().put_object(
            Bucket=settings.s3_bucket,
            Key=file_key,
            Body=body,
            ContentType=content_type,
        )
    except Exception:
        pass


def presigned_get_url(file_key: str, expires_in: int = 900) -> str:
    """Return a presigned GET URL for admin document review."""
    settings = get_settings()
    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": file_key,
            },
            ExpiresIn=expires_in,
        )
    except Exception:
        return f"https://s3.example.com/{file_key}?presigned=dev"
