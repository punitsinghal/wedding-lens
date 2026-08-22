"""Tests for the R2 (S3-compatible) object storage service module."""
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.exceptions import ClientError

from app.services import r2

BUCKET = "test-bucket"
ENDPOINT = "https://accountid.r2.cloudflarestorage.com"


def _local_signing_client():
    """A real boto3 S3 client for local HMAC signing — no network call, no
    real credentials needed."""
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="auto",
    )


def _client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": code, "Message": "boom"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation_name=operation,
    )


# ---------------------------------------------------------------------------
# generate_get_url
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_generate_get_url_structure(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_get_url("events/e1/p1.jpg", ttl_seconds=21600)

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert "events/e1/p1.jpg" in parsed.path
    assert BUCKET in parsed.netloc or BUCKET in parsed.path
    assert qs["X-Amz-Expires"] == ["21600"]


@patch("app.services.r2.settings")
def test_generate_get_url_with_response_headers(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_get_url(
            "events/e1/p1.jpg",
            response_content_disposition="attachment; filename=p1.jpg",
            response_content_type="image/jpeg",
        )

    qs = parse_qs(urlparse(url).query)
    assert qs["response-content-disposition"] == ["attachment; filename=p1.jpg"]
    assert qs["response-content-type"] == ["image/jpeg"]


@patch("app.services.r2.settings")
def test_generate_get_url_default_ttl(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_get_url("events/e1/p1.jpg")

    qs = parse_qs(urlparse(url).query)
    assert qs["X-Amz-Expires"] == ["21600"]


@patch("app.services.r2.settings")
def test_generate_get_url_wraps_signing_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.generate_presigned_url.side_effect = _client_error(
        "InvalidAccessKeyId", 403, "GetObject"
    )
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.generate_get_url("events/e1/p1.jpg")


# ---------------------------------------------------------------------------
# generate_put_url
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_generate_put_url_structure(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_put_url("events/e1/guest-upload.jpg", ttl_seconds=900)

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert "events/e1/guest-upload.jpg" in parsed.path
    assert qs["X-Amz-Expires"] == ["900"]


@patch("app.services.r2.settings")
def test_generate_put_url_default_ttl(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_put_url("events/e1/guest-upload.jpg")

    qs = parse_qs(urlparse(url).query)
    assert qs["X-Amz-Expires"] == ["900"]


# ---------------------------------------------------------------------------
# create_multipart_upload
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_create_multipart_upload_returns_upload_id(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.create_multipart_upload.return_value = {"UploadId": "abc123"}
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        upload_id = r2.create_multipart_upload("events/e1/photo.jpg")

    assert upload_id == "abc123"
    mock_client.create_multipart_upload.assert_called_once_with(
        Bucket=BUCKET, Key="events/e1/photo.jpg"
    )


@patch("app.services.r2.settings")
def test_create_multipart_upload_wraps_client_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.create_multipart_upload.side_effect = _client_error(
        "InternalError", 500, "CreateMultipartUpload"
    )
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.create_multipart_upload("events/e1/photo.jpg")


# ---------------------------------------------------------------------------
# generate_upload_part_url
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_generate_upload_part_url_structure(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    with patch("app.services.r2.get_r2_client", return_value=_local_signing_client()):
        url = r2.generate_upload_part_url(
            "events/e1/photo.jpg", upload_id="abc123", part_number=1
        )

    qs = parse_qs(urlparse(url).query)
    assert qs["uploadId"] == ["abc123"]
    assert qs["partNumber"] == ["1"]
    assert qs["X-Amz-Expires"] == ["3600"]


# ---------------------------------------------------------------------------
# complete_multipart_upload
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_complete_multipart_upload_calls_client_correctly(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    parts = [{"PartNumber": 1, "ETag": "etag1"}, {"PartNumber": 2, "ETag": "etag2"}]
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        r2.complete_multipart_upload("events/e1/photo.jpg", "abc123", parts)

    mock_client.complete_multipart_upload.assert_called_once_with(
        Bucket=BUCKET,
        Key="events/e1/photo.jpg",
        UploadId="abc123",
        MultipartUpload={"Parts": parts},
    )


@patch("app.services.r2.settings")
def test_complete_multipart_upload_wraps_client_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.complete_multipart_upload.side_effect = _client_error(
        "InvalidPart", 400, "CompleteMultipartUpload"
    )
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.complete_multipart_upload("events/e1/photo.jpg", "abc123", [])


# ---------------------------------------------------------------------------
# head_object
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_head_object_returns_true_when_exists(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.return_value = {}
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.head_object("events/e1/photo.jpg") is True

    mock_client.head_object.assert_called_once_with(
        Bucket=BUCKET, Key="events/e1/photo.jpg"
    )


@patch("app.services.r2.settings")
def test_head_object_returns_false_on_404(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _client_error("404", 404, "HeadObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.head_object("events/e1/missing.jpg") is False


@patch("app.services.r2.settings")
def test_head_object_returns_false_on_no_such_key(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _client_error(
        "NoSuchKey", 404, "HeadObject"
    )
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.head_object("events/e1/missing.jpg") is False


@patch("app.services.r2.settings")
def test_head_object_raises_on_other_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _client_error(
        "AccessDenied", 403, "HeadObject"
    )
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.head_object("events/e1/photo.jpg")


# ---------------------------------------------------------------------------
# get_object_size
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_get_object_size_returns_content_length(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ContentLength": 12345}
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.get_object_size("events/e1/photo.jpg") == 12345


@patch("app.services.r2.settings")
def test_get_object_size_returns_none_when_missing(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _client_error("404", 404, "HeadObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.get_object_size("events/e1/missing.jpg") is None


@patch("app.services.r2.settings")
def test_get_object_size_raises_on_other_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.head_object.side_effect = _client_error("AccessDenied", 403, "HeadObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.get_object_size("events/e1/photo.jpg")


# ---------------------------------------------------------------------------
# read_range
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_read_range_returns_body_bytes(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_body = MagicMock()
    mock_body.read.return_value = b"\xff\xd8\xff\xe0"
    mock_client = MagicMock()
    mock_client.get_object.return_value = {"Body": mock_body}
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        result = r2.read_range("events/e1/photo.jpg", 0, 15)

    assert result == b"\xff\xd8\xff\xe0"
    mock_client.get_object.assert_called_once_with(
        Bucket=BUCKET, Key="events/e1/photo.jpg", Range="bytes=0-15"
    )


@patch("app.services.r2.settings")
def test_read_range_wraps_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.get_object.side_effect = _client_error("AccessDenied", 403, "GetObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.read_range("events/e1/photo.jpg", 0, 15)


# ---------------------------------------------------------------------------
# download_object
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_download_object_returns_body_bytes(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_body = MagicMock()
    mock_body.read.return_value = b"the-full-object-bytes"
    mock_client = MagicMock()
    mock_client.get_object.return_value = {"Body": mock_body}
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        result = r2.download_object("events/e1/photo.jpg")

    assert result == b"the-full-object-bytes"
    mock_client.get_object.assert_called_once_with(
        Bucket=BUCKET, Key="events/e1/photo.jpg"
    )


@patch("app.services.r2.settings")
def test_download_object_wraps_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.get_object.side_effect = _client_error("AccessDenied", 403, "GetObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.download_object("events/e1/photo.jpg")


# ---------------------------------------------------------------------------
# put_object
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_put_object_calls_client_correctly(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        r2.put_object("events/e1/thumbs/p1.webp", b"webp-bytes", "image/webp")

    mock_client.put_object.assert_called_once_with(
        Bucket=BUCKET,
        Key="events/e1/thumbs/p1.webp",
        Body=b"webp-bytes",
        ContentType="image/webp",
    )


@patch("app.services.r2.settings")
def test_put_object_wraps_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.put_object.side_effect = _client_error("InternalError", 500, "PutObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.put_object("events/e1/thumbs/p1.webp", b"webp-bytes", "image/webp")


# ---------------------------------------------------------------------------
# delete_object
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_delete_object_calls_client_correctly(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        r2.delete_object("events/e1/photo.jpg")

    mock_client.delete_object.assert_called_once_with(Bucket=BUCKET, Key="events/e1/photo.jpg")


@patch("app.services.r2.settings")
def test_delete_object_wraps_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.delete_object.side_effect = _client_error("AccessDenied", 403, "DeleteObject")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.delete_object("events/e1/photo.jpg")


# ---------------------------------------------------------------------------
# list_parts
# ---------------------------------------------------------------------------


@patch("app.services.r2.settings")
def test_list_parts_returns_sorted_parts_across_pages(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Parts": [{"PartNumber": 2, "ETag": '"etag2"'}]},
        {"Parts": [{"PartNumber": 1, "ETag": '"etag1"'}]},
    ]
    mock_client = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        parts = r2.list_parts("events/e1/photo.jpg", "upload-123")

    assert parts == [
        {"PartNumber": 1, "ETag": '"etag1"'},
        {"PartNumber": 2, "ETag": '"etag2"'},
    ]
    mock_client.get_paginator.assert_called_once_with("list_parts")
    mock_paginator.paginate.assert_called_once_with(
        Bucket=BUCKET, Key="events/e1/photo.jpg", UploadId="upload-123"
    )


@patch("app.services.r2.settings")
def test_list_parts_empty_when_no_parts_uploaded_yet(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Parts": []}]
    mock_client = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        assert r2.list_parts("events/e1/photo.jpg", "upload-123") == []


@patch("app.services.r2.settings")
def test_list_parts_wraps_error(mock_settings):
    mock_settings.R2_BUCKET_NAME = BUCKET
    mock_client = MagicMock()
    mock_client.get_paginator.side_effect = _client_error("NoSuchUpload", 404, "ListParts")
    with patch("app.services.r2.get_r2_client", return_value=mock_client):
        with pytest.raises(r2.StorageUnavailableError):
            r2.list_parts("events/e1/photo.jpg", "upload-123")


# ---------------------------------------------------------------------------
# get_r2_client — lazy singleton
# ---------------------------------------------------------------------------


def test_get_r2_client_is_lazy_singleton():
    r2._client = None
    with patch("app.services.r2.settings") as mock_settings, \
         patch("app.services.r2.boto3.client") as mock_boto_client:
        mock_settings.R2_ENDPOINT = ENDPOINT
        mock_settings.R2_ACCESS_KEY_ID = "id"
        mock_settings.R2_SECRET_ACCESS_KEY = "secret"
        mock_boto_client.return_value = MagicMock()

        client1 = r2.get_r2_client()
        client2 = r2.get_r2_client()

    assert client1 is client2
    mock_boto_client.assert_called_once_with(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id="id",
        aws_secret_access_key="secret",
        region_name="auto",
    )
    r2._client = None
