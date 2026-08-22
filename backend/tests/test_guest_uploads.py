"""Tests for the guest photo upload endpoints (docs/features/guest-uploads).

Guests upload directly to R2 via a presigned URL, so these tests mock
app.services.r2 rather than exercising real S3-compatible calls or local
disk writes (see tests/test_uploads.py for the equivalent pattern on the
photographer chunked-upload flow).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services import r2
from app.services.auth import create_access_token, hash_password
from app.services.guest_auth import create_guest_token, guest_upload_rate_limiter, upload_counter

# Real JPEG magic bytes — required wherever the endpoint sniffs actual file
# content (app/services/image_format.py), not just the client-supplied
# filename extension.
JPEG_HEADER = b"\xff\xd8fake-jpeg-bytes"


@pytest.fixture(autouse=True)
def reset_upload_counter():
    """Clear the in-process upload counter before and after every test."""
    upload_counter.clear_all()
    yield
    upload_counter.clear_all()


@pytest.fixture(autouse=True)
def reset_upload_rate_limiter():
    """Clear the in-process abuse rate limiter before and after every test."""
    guest_upload_rate_limiter.clear_all()
    yield
    guest_upload_rate_limiter.clear_all()


@pytest.fixture(autouse=True)
def noop_process_photo():
    with patch("app.routers.guest_uploads.process_photo", new=AsyncMock()):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="guest-upload-owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def owner_headers(owner: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(owner.id))}"}


@pytest_asyncio.fixture
async def event(db: AsyncSession, owner: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Guest Upload Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"guest-upload-test-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
        guest_uploads_enabled=True,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest_asyncio.fixture
async def other_event(db: AsyncSession, owner: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Other Wedding",
        bride_name="Carol",
        groom_name="Dave",
        slug=f"other-wedding-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
        guest_uploads_enabled=True,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


def _guest_headers(event: Event, sid: str | None = None) -> dict:
    token = create_guest_token(str(event.id), sid=sid)
    return {"Authorization": f"Bearer {token}"}


def _initiate(
    client: AsyncClient,
    event: Event,
    headers: dict,
    filename: str = "photo.jpg",
    file_size_bytes: int = len(JPEG_HEADER),
    display_name: str | None = None,
):
    body = {"filename": filename, "file_size_bytes": file_size_bytes}
    if display_name is not None:
        body["display_name"] = display_name
    return client.post(
        f"/api/v1/events/{event.id}/guest-uploads/initiate",
        headers=headers,
        json=body,
    )


def _complete(
    client: AsyncClient,
    event: Event,
    photo_id,
    headers: dict,
    filename: str = "photo.jpg",
    display_name: str | None = None,
):
    body = {"filename": filename}
    if display_name is not None:
        body["display_name"] = display_name
    return client.post(
        f"/api/v1/events/{event.id}/guest-uploads/{photo_id}/complete",
        headers=headers,
        json=body,
    )


async def _initiate_and_complete(
    client: AsyncClient,
    event: Event,
    headers: dict,
    filename: str = "photo.jpg",
    file_size_bytes: int = len(JPEG_HEADER),
    display_name: str | None = None,
    header_bytes: bytes = JPEG_HEADER,
    object_size: int | None = None,
):
    """Drive the full initiate -> complete happy path, mocking R2 throughout."""
    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(
            client, event, headers, filename=filename, file_size_bytes=file_size_bytes, display_name=display_name
        )
    assert init_resp.status_code == 201, init_resp.text
    photo_id = init_resp.json()["photo_id"]

    size = object_size if object_size is not None else len(header_bytes)
    with (
        patch("app.routers.guest_uploads.r2.get_object_size", return_value=size),
        patch("app.routers.guest_uploads.r2.read_range", return_value=header_bytes[:16]),
    ):
        complete_resp = await _complete(
            client, event, photo_id, headers, filename=filename, display_name=display_name
        )
    return init_resp, complete_resp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_upload(client: AsyncClient, event: Event, db: AsyncSession):
    headers = _guest_headers(event)
    init_resp, complete_resp = await _initiate_and_complete(client, event, headers, display_name="Priya")

    assert "X-Guest-Token" in init_resp.headers
    assert complete_resp.status_code == 201, complete_resp.text
    body = complete_resp.json()
    assert body["event_id"] == str(event.id)
    assert body["album_id"] is None
    assert body["filename"] == "photo.jpg"
    assert body["processing_status"] == "pending"
    assert "X-Guest-Token" in complete_resp.headers

    photo_id = uuid.UUID(body["id"])
    result = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = result.scalar_one()
    assert photo.uploaded_by == "guest"
    assert photo.guest_display_name == "Priya"
    assert photo.storage_path == f"events/{event.id}/{photo_id}_photo.jpg"
    assert photo.file_size == len(JPEG_HEADER)


@pytest.mark.asyncio
async def test_complete_enqueues_face_processing(client: AsyncClient, event: Event):
    with patch("app.routers.guest_uploads.process_photo", new=AsyncMock()) as mock_process:
        _, complete_resp = await _initiate_and_complete(client, event, _guest_headers(event))
    assert complete_resp.status_code == 201
    mock_process.assert_called_once()


# ---------------------------------------------------------------------------
# Guest uploads disabled → 403 (checked at both initiate and complete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_guest_uploads_disabled_returns_403(
    client: AsyncClient, event: Event, db: AsyncSession
):
    event.guest_uploads_enabled = False
    db.add(event)
    await db.commit()

    resp = await _initiate(client, event, _guest_headers(event))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Guest uploads are disabled for this event."


@pytest.mark.asyncio
async def test_complete_guest_uploads_disabled_returns_403(
    client: AsyncClient, event: Event, db: AsyncSession
):
    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(client, event, _guest_headers(event))
    photo_id = init_resp.json()["photo_id"]

    event.guest_uploads_enabled = False
    db.add(event)
    await db.commit()

    resp = await _complete(client, event, photo_id, _guest_headers(event))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Guest uploads are disabled for this event."


# ---------------------------------------------------------------------------
# Session cap — 20 accepted, 21st rejected (enforced at initiate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_cap_rejects_21st_upload(client: AsyncClient, event: Event):
    headers = _guest_headers(event, sid="fixed-session")

    for i in range(20):
        _, complete_resp = await _initiate_and_complete(
            client, event, headers, filename=f"photo-{i}.jpg"
        )
        assert complete_resp.status_code == 201, complete_resp.text

    resp = await _initiate(client, event, headers, filename="photo-21.jpg")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Upload limit reached for this session."


# ---------------------------------------------------------------------------
# Abuse rate limit — 40/hour per (event_id, ip), independent of session cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_41st_upload_across_sessions_returns_429(
    client: AsyncClient, event: Event
):
    """A fresh guest session resets the 20-per-session cap but not the
    per-IP abuse ceiling — 41 uploads across multiple sessions still 429s."""
    # Two sessions of 20 each, both under the per-session cap, same client IP
    for session in range(2):
        headers = _guest_headers(event, sid=f"session-{session}")
        for i in range(20):
            _, complete_resp = await _initiate_and_complete(
                client, event, headers, filename=f"s{session}-{i}.jpg"
            )
            assert complete_resp.status_code == 201, complete_resp.text

    # 41st upload, on a brand-new (unfilled) session — still rate-limited
    resp = await _initiate(client, event, _guest_headers(event, sid="session-3"))
    assert resp.status_code == 429
    assert resp.json()["detail"] == "rate_limited"
    assert "retry-after" in resp.headers
    assert int(resp.headers["retry-after"]) > 0


# ---------------------------------------------------------------------------
# Validation errors — initiate (metadata only, no file bytes yet)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_unsupported_extension_returns_422(client: AsyncClient, event: Event):
    resp = await _initiate(client, event, _guest_headers(event), filename="photo.heic")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Only JPEG and PNG files are accepted"


@pytest.mark.asyncio
async def test_initiate_oversized_file_size_returns_422(client: AsyncClient, event: Event):
    resp = await _initiate(
        client, event, _guest_headers(event), file_size_bytes=25 * 1024 * 1024 + 1
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "File exceeds the 25 MB limit"


@pytest.mark.asyncio
async def test_initiate_display_name_over_100_chars_returns_422(client: AsyncClient, event: Event):
    resp = await _initiate(client, event, _guest_headers(event), display_name="x" * 101)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Display name must be 100 characters or fewer."


@pytest.mark.asyncio
async def test_initiate_returns_503_when_r2_unavailable(client: AsyncClient, event: Event):
    with patch(
        "app.routers.guest_uploads.r2.generate_put_url",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await _initiate(client, event, _guest_headers(event))
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Validation errors — complete (object now exists in R2, verified there)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_missing_object_returns_422(client: AsyncClient, event: Event):
    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(client, event, _guest_headers(event))
    photo_id = init_resp.json()["photo_id"]

    with patch("app.routers.guest_uploads.r2.get_object_size", return_value=None):
        resp = await _complete(client, event, photo_id, _guest_headers(event))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Upload not found or incomplete"


@pytest.mark.asyncio
async def test_complete_oversized_object_returns_422_and_deletes(client: AsyncClient, event: Event):
    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(client, event, _guest_headers(event))
    photo_id = init_resp.json()["photo_id"]

    with (
        patch("app.routers.guest_uploads.r2.get_object_size", return_value=25 * 1024 * 1024 + 1),
        patch("app.routers.guest_uploads.r2.delete_object") as mock_delete,
    ):
        resp = await _complete(client, event, photo_id, _guest_headers(event))

    assert resp.status_code == 422
    assert resp.json()["detail"] == "File exceeds the 25 MB limit"
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_complete_heic_bytes_with_spoofed_jpg_filename_returns_422_and_deletes(
    client: AsyncClient, event: Event
):
    """A real HEIC file (or any non-JPEG/PNG bytes) must be rejected even
    when the client claims a .jpg filename — the magic-byte sniff of the
    object actually stored in R2 is authoritative, not the filename."""
    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"rest-of-heic-file"

    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(client, event, _guest_headers(event), filename="photo.jpg")
    photo_id = init_resp.json()["photo_id"]

    with (
        patch("app.routers.guest_uploads.r2.get_object_size", return_value=len(heic_bytes)),
        patch("app.routers.guest_uploads.r2.read_range", return_value=heic_bytes[:16]),
        patch("app.routers.guest_uploads.r2.delete_object") as mock_delete,
    ):
        resp = await _complete(client, event, photo_id, _guest_headers(event), filename="photo.jpg")

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Only JPEG and PNG files are accepted"
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_complete_returns_503_when_r2_unavailable(client: AsyncClient, event: Event):
    with patch("app.routers.guest_uploads.r2.generate_put_url", return_value="https://r2.example.com/put"):
        init_resp = await _initiate(client, event, _guest_headers(event))
    photo_id = init_resp.json()["photo_id"]

    with patch(
        "app.routers.guest_uploads.r2.get_object_size",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await _complete(client, event, photo_id, _guest_headers(event))
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Revoked guest access → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoked_guest_access_returns_401(
    client: AsyncClient, event: Event, db: AsyncSession
):
    event.guest_access_enabled = False
    db.add(event)
    await db.commit()

    resp = await _initiate(client, event, _guest_headers(event))
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cross-event isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guest_token_for_event_a_cannot_initiate_upload_to_event_b(
    client: AsyncClient, event: Event, other_event: Event
):
    headers = _guest_headers(event)
    resp = await client.post(
        f"/api/v1/events/{other_event.id}/guest-uploads/initiate",
        headers=headers,
        json={"filename": "photo.jpg", "file_size_bytes": len(JPEG_HEADER)},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# uploaded_by / guest_display_name surfaced via gallery + owner photo list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uploaded_by_and_display_name_in_gallery_and_owner_list(
    client: AsyncClient, event: Event, owner_headers: dict, db: AsyncSession
):
    _, complete_resp = await _initiate_and_complete(
        client, event, _guest_headers(event), display_name="Priya"
    )
    assert complete_resp.status_code == 201
    photo_id = complete_resp.json()["id"]

    # Owner photo list
    owner_resp = await client.get(
        f"/api/v1/events/{event.id}/photos", headers=owner_headers
    )
    assert owner_resp.status_code == 200
    owner_item = next(i for i in owner_resp.json()["items"] if i["id"] == photo_id)
    assert owner_item["uploaded_by"] == "guest"
    assert owner_item["guest_display_name"] == "Priya"

    # Guest gallery list
    gallery_resp = await client.get(
        f"/api/v1/events/{event.id}/gallery", headers=_guest_headers(event)
    )
    assert gallery_resp.status_code == 200
    gallery_item = next(p for p in gallery_resp.json()["photos"] if p["id"] == photo_id)
    assert gallery_item["uploaded_by"] == "guest"
    assert gallery_item["guest_display_name"] == "Priya"


@pytest.mark.asyncio
async def test_blank_display_name_attributed_as_none(
    client: AsyncClient, event: Event, owner_headers: dict
):
    _, complete_resp = await _initiate_and_complete(client, event, _guest_headers(event))
    assert complete_resp.status_code == 201
    photo_id = complete_resp.json()["id"]

    owner_resp = await client.get(
        f"/api/v1/events/{event.id}/photos", headers=owner_headers
    )
    item = next(i for i in owner_resp.json()["items"] if i["id"] == photo_id)
    assert item["guest_display_name"] is None


# ---------------------------------------------------------------------------
# EventPublicOut now exposes guest_uploads_enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_public_out_includes_guest_uploads_enabled(
    client: AsyncClient, event: Event
):
    resp = await client.get(f"/api/v1/events/by-slug/{event.slug}")
    assert resp.status_code == 200
    assert resp.json()["guest_uploads_enabled"] is True
