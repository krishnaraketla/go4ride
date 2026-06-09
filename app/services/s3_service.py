"""S3 presigned URL helpers for driver KYC document upload and admin review."""

from app.core.config import get_settings


def _s3_client():
    import boto3  # type: ignore[import]

    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


def presigned_put_url(file_key: str, content_type: str, expires_in: int = 900) -> str:
    """Return a presigned PUT URL, or a dev placeholder when S3 is unavailable."""
    settings = get_settings()
    try:
        return _s3_client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    except Exception:
        return f"https://s3.example.com/{file_key}?presigned=dev"


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
