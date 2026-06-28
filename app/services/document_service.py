"""
Document collection: S3 uploads, pre-signed URLs, upload token management.
"""
import boto3
import uuid
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
    "image/tiff",
}

MAX_FILE_SIZE_MB = 25


def generate_upload_token() -> str:
    return str(uuid.uuid4()).replace("-", "")


def generate_s3_key(lead_id: str, doc_type: str, file_name: str) -> str:
    ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
    return f"leads/{lead_id}/{doc_type}/{uuid.uuid4()}.{ext}"


def generate_presigned_upload_url(s3_key: str, mime_type: str, expires_seconds: int = 3600) -> str:
    """Generate a pre-signed S3 PUT URL for direct client upload."""
    url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": s3_key,
            "ContentType": mime_type,
        },
        ExpiresIn=expires_seconds,
    )
    return url


def generate_presigned_download_url(s3_key: str, expires_seconds: int = 3600) -> str:
    """Generate a pre-signed S3 GET URL for secure document access."""
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_seconds,
    )
    return url


def get_document_upload_page_url(upload_token: str) -> str:
    """Public URL for the document upload page (sent via SMS)."""
    return f"{settings.APP_URL}/upload/{upload_token}"


def upload_file_to_s3(file_bytes: bytes, s3_key: str, mime_type: str) -> str:
    """Upload file bytes to S3. Returns the S3 URL."""
    s3_client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=s3_key,
        Body=file_bytes,
        ContentType=mime_type,
        ServerSideEncryption="AES256",
    )
    return f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"


def delete_s3_object(s3_key: str) -> None:
    try:
        s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    except ClientError as e:
        logger.error(f"Failed to delete S3 object {s3_key}: {e}")
