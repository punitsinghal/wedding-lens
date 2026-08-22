"""Tests for chunked photo upload endpoints (R2-backed multipart flow)."""
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services import r2
from app.services.auth import create_access_token, hash_password

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="upload-owner@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def other_user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="upload-other@example.com",
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


@pytest.fixture
def other_headers(other_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(other_user.id))}"}


@pytest_asyncio.fixture
async def event(db: AsyncSession, owner: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Upload Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"upload-test-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


# ---------------------------------------------------------------------------
# Helper: create a small fake JPEG (valid magic bytes)
# ---------------------------------------------------------------------------


def _fake_jpeg(size: int = 100) -> bytes:
    """Return bytes with JPEG magic header, padded to `size` bytes."""
    header = b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4)
    return header[:size]


def _fake_png(size: int = 100) -> bytes:
    """Return bytes with PNG magic header, padded to `size` bytes."""
    header = b"\x89PNG\r\n\x1a\n" + b"\x00" * (size - 8)
    return header[:size]


def _parts(n: int) -> list[dict]:
    """A list of n received parts, 1-indexed PartNumbers, as list_parts would return."""
    return [{"PartNumber": i + 1, "ETag": f"etag-{i}"} for i in range(n)]


# ---------------------------------------------------------------------------
# 1. Initiate upload — 201 with session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_upload_returns_201(
    client: AsyncClient, owner_headers: dict, event: Event
):
    with patch("app.routers.uploads.r2.create_multipart_upload", return_value="up-1"):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "photo.jpg",
                "file_size_bytes": 16 * 1024 * 1024,  # 16 MB → 2 chunks
                "content_hash": "abc123def456",
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert body["chunk_size_bytes"] == CHUNK_SIZE
    assert body["total_chunks"] == 2
    uuid.UUID(body["session_id"])  # assert parseable


@pytest.mark.asyncio
async def test_initiate_upload_calculates_chunks_correctly(
    client: AsyncClient, owner_headers: dict, event: Event
):
    """A 1-byte file → 1 chunk; a CHUNK_SIZE+1-byte file → 2 chunks."""
    with patch("app.routers.uploads.r2.create_multipart_upload", return_value="up-1"):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "tiny.jpg",
                "file_size_bytes": 1,
                "content_hash": "hash001",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["total_chunks"] == 1

    with patch("app.routers.uploads.r2.create_multipart_upload", return_value="up-2"):
        resp2 = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "big.jpg",
                "file_size_bytes": CHUNK_SIZE + 1,
                "content_hash": "hash002",
            },
        )
    assert resp2.status_code == 201
    assert resp2.json()["total_chunks"] == 2


@pytest.mark.asyncio
async def test_initiate_upload_requires_auth(client: AsyncClient, event: Event):
    resp = await client.post(
        f"/api/v1/events/{event.id}/uploads",
        json={"filename": "x.jpg", "file_size_bytes": 100, "content_hash": "h"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_initiate_upload_rejects_non_owner(
    client: AsyncClient, other_headers: dict, event: Event
):
    resp = await client.post(
        f"/api/v1/events/{event.id}/uploads",
        headers=other_headers,
        json={"filename": "x.jpg", "file_size_bytes": 100, "content_hash": "h"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_initiate_upload_rejects_invalid_extension(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.post(
        f"/api/v1/events/{event.id}/uploads",
        headers=owner_headers,
        json={"filename": "video.mp4", "file_size_bytes": 1024, "content_hash": "h"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_initiate_upload_rejects_oversized_file(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.post(
        f"/api/v1/events/{event.id}/uploads",
        headers=owner_headers,
        json={
            "filename": "big.jpg",
            "file_size_bytes": 26 * 1024 * 1024,  # 26 MB — over limit
            "content_hash": "h",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_initiate_upload_returns_503_when_r2_unavailable(
    client: AsyncClient, owner_headers: dict, event: Event
):
    with patch(
        "app.routers.uploads.r2.create_multipart_upload",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "photo.jpg",
                "file_size_bytes": 1024,
                "content_hash": "unavailable-hash",
            },
        )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 2. Dedup: initiate same content_hash → 200 duplicate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_upload_dedup_existing_photo(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession
):
    """If a photo with the same content_hash already exists → 200 {status: duplicate}."""
    existing_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="existing.jpg",
        storage_path=f"events/{event.id}/existing.jpg",
        file_size=1024,
        content_hash="dedup-hash-123",
        processing_status="complete",
    )
    db.add(existing_photo)
    await db.commit()

    resp = await client.post(
        f"/api/v1/events/{event.id}/uploads",
        headers=owner_headers,
        json={
            "filename": "same.jpg",
            "file_size_bytes": 1024,
            "content_hash": "dedup-hash-123",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "duplicate"
    assert body["photo_id"] == str(existing_photo.id)


@pytest.mark.asyncio
async def test_initiate_upload_dedup_in_flight_session(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """If an in-progress session with the same content_hash exists → 200 {status: resumable}."""
    photo_id = uuid.uuid4()
    existing_session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="inflight.jpg",
        file_size_bytes=5 * 1024 * 1024,
        content_hash="inflight-hash-456",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=3,
        received_chunks=[],
        status="in_progress",
        photo_id=photo_id,
        r2_upload_id="up-inflight",
    )
    db.add(existing_session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.list_parts", return_value=_parts(2)
    ) as mock_list_parts:
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "inflight.jpg",
                "file_size_bytes": 5 * 1024 * 1024,
                "content_hash": "inflight-hash-456",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resumable"
    assert body["session_id"] == str(existing_session.id)
    assert sorted(body["received_chunks"]) == [0, 1]
    assert body["total_chunks"] == 3
    mock_list_parts.assert_called_once()
    called_key, called_upload_id = mock_list_parts.call_args[0]
    assert called_key == f"events/{event.id}/{photo_id}.jpg"
    assert called_upload_id == "up-inflight"


@pytest.mark.asyncio
async def test_initiate_upload_dedup_in_flight_session_r2_unavailable(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    existing_session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="inflight2.jpg",
        file_size_bytes=5 * 1024 * 1024,
        content_hash="inflight-hash-789",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=3,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-inflight2",
    )
    db.add(existing_session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.list_parts",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "inflight2.jpg",
                "file_size_bytes": 5 * 1024 * 1024,
                "content_hash": "inflight-hash-789",
            },
        )

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 3. Chunk upload URL → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_chunk_upload_url_returns_200(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """GET /chunks/{i}/url returns a presigned URL for a valid session/chunk."""
    photo_id = uuid.uuid4()
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="test.jpg",
        file_size_bytes=CHUNK_SIZE,
        content_hash="chunk-hash-789",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=photo_id,
        r2_upload_id="up-3",
    )
    db.add(session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.generate_upload_part_url",
        return_value="https://r2.example.com/signed-part-url",
    ) as mock_sign:
        resp = await client.get(
            f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/0/url",
            headers=owner_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["chunk_index"] == 0
    assert body["url"] == "https://r2.example.com/signed-part-url"
    mock_sign.assert_called_once_with(f"events/{event.id}/{photo_id}.jpg", "up-3", 1)


@pytest.mark.asyncio
async def test_get_chunk_upload_url_rejects_out_of_range(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="test.jpg",
        file_size_bytes=CHUNK_SIZE,
        content_hash="range-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-4",
    )
    db.add(session)
    await db.commit()

    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/5/url",
        headers=owner_headers,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_chunk_upload_url_rejects_when_not_in_progress(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="test.jpg",
        file_size_bytes=CHUNK_SIZE,
        content_hash="done-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="complete",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-5",
    )
    db.add(session)
    await db.commit()

    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/0/url",
        headers=owner_headers,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_chunk_upload_url_not_found(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{uuid.uuid4()}/chunks/0/url",
        headers=owner_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_chunk_upload_url_r2_unavailable(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="test.jpg",
        file_size_bytes=CHUNK_SIZE,
        content_hash="unavailable-chunk-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-6",
    )
    db.add(session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.generate_upload_part_url",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.get(
            f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/0/url",
            headers=owner_headers,
        )

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 4. Complete upload → 201 with photo_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_upload_returns_201(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """POST /complete completes the multipart upload and returns {photo_id}."""
    photo_id = uuid.uuid4()
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="final.jpg",
        file_size_bytes=len(_fake_jpeg(500)),
        content_hash="complete-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=photo_id,
        r2_upload_id="up-7",
    )
    db.add(session)
    await db.commit()

    jpeg_header = _fake_jpeg(16)

    with patch("app.routers.uploads.r2.list_parts", return_value=_parts(1)), \
         patch("app.routers.uploads.r2.complete_multipart_upload") as mock_complete, \
         patch("app.routers.uploads.r2.head_object", return_value=True), \
         patch("app.routers.uploads.r2.read_range", return_value=jpeg_header), \
         patch("app.routers.uploads.process_photo"):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["photo_id"] == str(photo_id)
    mock_complete.assert_called_once()


@pytest.mark.asyncio
async def test_complete_upload_creates_photo_record(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """After /complete, a Photo row exists in the DB with the correct metadata."""
    from sqlalchemy import select

    content_hash = "complete-hash-002"
    photo_id = uuid.uuid4()
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="wedding.jpg",
        file_size_bytes=400,
        content_hash=content_hash,
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=photo_id,
        r2_upload_id="up-8",
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.r2.list_parts", return_value=_parts(1)), \
         patch("app.routers.uploads.r2.complete_multipart_upload"), \
         patch("app.routers.uploads.r2.head_object", return_value=True), \
         patch("app.routers.uploads.r2.read_range", return_value=_fake_jpeg(16)), \
         patch("app.routers.uploads.process_photo"):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
    returned_photo_id = uuid.UUID(resp.json()["photo_id"])
    assert returned_photo_id == photo_id

    result = await db.execute(select(Photo).where(Photo.id == returned_photo_id))
    photo = result.scalar_one_or_none()
    assert photo is not None
    assert photo.event_id == event.id
    assert photo.content_hash == content_hash
    assert photo.processing_status == "pending"
    assert photo.filename == "wedding.jpg"
    assert photo.storage_path == f"events/{event.id}/{photo_id}.jpg"


@pytest.mark.asyncio
async def test_complete_upload_missing_chunks_returns_422(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """If not all parts are present in R2, /complete returns 422 with missing indices."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="incomplete.jpg",
        file_size_bytes=CHUNK_SIZE * 3,
        content_hash="incomplete-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=3,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-9",
    )
    db.add(session)
    await db.commit()

    # Parts 1 and 3 received (0-indexed 0 and 2) — chunk 1 missing
    parts_present = [{"PartNumber": 1, "ETag": "e0"}, {"PartNumber": 3, "ETag": "e2"}]

    with patch("app.routers.uploads.r2.list_parts", return_value=parts_present):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 422
    assert "1" in resp.json()["detail"]  # missing chunk 1 mentioned in error


@pytest.mark.asyncio
async def test_complete_upload_rejects_invalid_image(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """If assembled object is not JPEG/PNG, /complete returns 422 and deletes the object."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="fake.jpg",
        file_size_bytes=100,
        content_hash="invalid-image-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-10",
    )
    db.add(session)
    await db.commit()

    garbage = b"this is not an image" + b"\x00" * 80

    with patch("app.routers.uploads.r2.list_parts", return_value=_parts(1)), \
         patch("app.routers.uploads.r2.complete_multipart_upload"), \
         patch("app.routers.uploads.r2.head_object", return_value=True), \
         patch("app.routers.uploads.r2.read_range", return_value=garbage), \
         patch("app.routers.uploads.r2.delete_object") as mock_delete:
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 422
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_complete_upload_head_object_false_returns_503(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """If HEAD reports the object missing after a successful complete, return 503
    and do not insert a Photo row."""
    from sqlalchemy import select

    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="ghost.jpg",
        file_size_bytes=100,
        content_hash="ghost-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-11",
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.r2.list_parts", return_value=_parts(1)), \
         patch("app.routers.uploads.r2.complete_multipart_upload"), \
         patch("app.routers.uploads.r2.head_object", return_value=False):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 503

    result = await db.execute(select(Photo).where(Photo.content_hash == "ghost-hash"))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_complete_upload_r2_unavailable_returns_503(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="flaky.jpg",
        file_size_bytes=100,
        content_hash="flaky-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-12",
    )
    db.add(session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.list_parts",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 5. Resume — GET session → list received chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_returns_received_chunks(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """GET /{session_id} returns the list of received chunk indices, derived live from R2."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="resume.jpg",
        file_size_bytes=CHUNK_SIZE * 5,
        content_hash="resume-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=5,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-13",
    )
    db.add(session)
    await db.commit()

    parts_present = [
        {"PartNumber": 1, "ETag": "e0"},
        {"PartNumber": 2, "ETag": "e1"},
        {"PartNumber": 4, "ETag": "e3"},
    ]

    with patch("app.routers.uploads.r2.list_parts", return_value=parts_present):
        resp = await client.get(
            f"/api/v1/events/{event.id}/uploads/{session.id}",
            headers=owner_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == str(session.id)
    assert sorted(body["received_chunks"]) == [0, 1, 3]
    assert body["total_chunks"] == 5
    assert body["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_session_not_found(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{uuid.uuid4()}",
        headers=owner_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_wrong_event(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """Session exists but belongs to a different event → 404."""
    other_event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Other Event",
        bride_name="X",
        groom_name="Y",
        slug=f"other-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(other_event)
    await db.commit()

    session = UploadSession(
        id=uuid.uuid4(),
        event_id=other_event.id,
        uploader_id=owner.id,
        filename="cross.jpg",
        file_size_bytes=100,
        content_hash="cross-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-14",
    )
    db.add(session)
    await db.commit()

    # Query with wrong event_id (using `event` not `other_event`)
    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{session.id}",
        headers=owner_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_r2_unavailable_returns_503(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="flaky-status.jpg",
        file_size_bytes=CHUNK_SIZE,
        content_hash="flaky-status-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-15",
    )
    db.add(session)
    await db.commit()

    with patch(
        "app.routers.uploads.r2.list_parts",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.get(
            f"/api/v1/events/{event.id}/uploads/{session.id}",
            headers=owner_headers,
        )

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 6. PNG support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_upload_accepts_png(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """A valid PNG-magic object should be accepted by /complete."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="photo.png",
        file_size_bytes=200,
        content_hash="png-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id="up-16",
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.r2.list_parts", return_value=_parts(1)), \
         patch("app.routers.uploads.r2.complete_multipart_upload"), \
         patch("app.routers.uploads.r2.head_object", return_value=True), \
         patch("app.routers.uploads.r2.read_range", return_value=_fake_png(16)), \
         patch("app.routers.uploads.process_photo"):
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
