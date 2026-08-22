"""Cloudflare R2 (S3-compatible) object storage operations for photo files.

R2 is accessed via boto3's S3 client pointed at R2's endpoint (region "auto").
See docs/decisions/2026-08-22-cloudflare-r2-photo-storage.md and
docs/decisions/2026-08-22-presigned-url-image-delivery.md for the rationale.
"""
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

logger = logging.getLogger("weddinglens.r2")

_client = None


class StorageUnavailableError(Exception):
    """Raised when an R2/S3 operation fails for any underlying boto3 reason.

    Callers should catch this single exception type instead of reaching into
    boto3-specific exceptions, and must check for it before writing any DB
    row so a storage failure never leaves Postgres in an inconsistent state
    (REQ-22/23/24 in docs/features/photo-storage-migration/requirements.md).
    """


def get_r2_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    return _client


def generate_get_url(
    key: str,
    ttl_seconds: int = 21600,
    response_content_disposition: str | None = None,
    response_content_type: str | None = None,
) -> str:
    """Presigned GET URL for reading an object. Default TTL 6 hours.

    Local HMAC signing only — no network call to R2.
    """
    client = get_r2_client()
    params: dict = {"Bucket": settings.R2_BUCKET_NAME, "Key": key}
    if response_content_disposition is not None:
        params["ResponseContentDisposition"] = response_content_disposition
    if response_content_type is not None:
        params["ResponseContentType"] = response_content_type
    try:
        return client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl_seconds
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(f"Failed to sign GET URL for key {key}") from exc


def generate_put_url(key: str, ttl_seconds: int = 900) -> str:
    """Presigned single-shot PUT URL, for guest uploads and cover-photo uploads.

    Default TTL 15 minutes. Local HMAC signing only — no network call to R2.
    """
    client = get_r2_client()
    try:
        return client.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
            ExpiresIn=ttl_seconds,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(f"Failed to sign PUT URL for key {key}") from exc


def create_multipart_upload(key: str) -> str:
    """Start a multipart upload; returns the UploadId."""
    client = get_r2_client()
    try:
        resp = client.create_multipart_upload(
            Bucket=settings.R2_BUCKET_NAME, Key=key
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(
            f"Failed to create multipart upload for key {key}"
        ) from exc
    return resp["UploadId"]


def generate_upload_part_url(
    key: str, upload_id: str, part_number: int, ttl_seconds: int = 3600
) -> str:
    """Presigned UploadPart URL for one part of an in-progress multipart upload."""
    client = get_r2_client()
    try:
        return client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=ttl_seconds,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(
            f"Failed to sign upload_part URL for key {key} part {part_number}"
        ) from exc


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    """Complete a multipart upload. `parts` is [{"PartNumber": int, "ETag": str}, ...]."""
    client = get_r2_client()
    try:
        client.complete_multipart_upload(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(
            f"Failed to complete multipart upload for key {key}"
        ) from exc


def _is_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = error.get("Code")
    return status == 404 or code in ("404", "NoSuchKey", "NotFound")


def head_object(key: str) -> bool:
    """Return True if the object exists, False if it definitively does not.

    Raises StorageUnavailableError for any other failure (auth, network,
    etc.) — "doesn't exist" and "can't tell if it exists" require different
    caller behavior.
    """
    client = get_r2_client()
    try:
        client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except ClientError as exc:
        if _is_not_found(exc):
            return False
        raise StorageUnavailableError(f"Failed to head object for key {key}") from exc
    except BotoCoreError as exc:
        raise StorageUnavailableError(f"Failed to head object for key {key}") from exc


def get_object_size(key: str) -> int | None:
    """Return the object's size in bytes, or None if it does not exist.

    Raises StorageUnavailableError for any other failure.
    """
    client = get_r2_client()
    try:
        resp = client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except ClientError as exc:
        if _is_not_found(exc):
            return None
        raise StorageUnavailableError(f"Failed to head object for key {key}") from exc
    except BotoCoreError as exc:
        raise StorageUnavailableError(f"Failed to head object for key {key}") from exc
    return resp["ContentLength"]


def read_range(key: str, start: int, end: int) -> bytes:
    """Read an inclusive byte range [start, end] from an object (e.g. for a
    magic-byte sniff without downloading the whole object)."""
    client = get_r2_client()
    try:
        resp = client.get_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        return resp["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(f"Failed to read range for key {key}") from exc


def delete_object(key: str) -> None:
    """Delete a single object. Idempotent — deleting a missing key is not an error."""
    client = get_r2_client()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(f"Failed to delete key {key}") from exc


def list_parts(key: str, upload_id: str) -> list[dict]:
    """Return all currently-uploaded parts of an in-progress multipart upload,
    as [{"PartNumber": int, "ETag": str}, ...], sorted by part number.

    This is the source of truth for "which chunks has R2 actually received" —
    used instead of tracking received-chunk state in Postgres, which avoids
    the read-modify-write race that existed in the pre-migration local-disk
    implementation.
    """
    client = get_r2_client()
    parts: list[dict] = []
    try:
        paginator = client.get_paginator("list_parts")
        for page in paginator.paginate(
            Bucket=settings.R2_BUCKET_NAME, Key=key, UploadId=upload_id
        ):
            for part in page.get("Parts", []):
                parts.append(
                    {"PartNumber": part["PartNumber"], "ETag": part["ETag"]}
                )
    except (ClientError, BotoCoreError) as exc:
        raise StorageUnavailableError(
            f"Failed to list parts for key {key} upload {upload_id}"
        ) from exc
    return sorted(parts, key=lambda p: p["PartNumber"])
