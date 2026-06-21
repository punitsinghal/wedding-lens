"""Tests for chunked photo upload endpoints."""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services.auth import create_access_token, hash_password

CHUNK_SIZE = 2097152  # 2 MB


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


# ---------------------------------------------------------------------------
# 1. Initiate upload — 201 with session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_upload_returns_201(
    client: AsyncClient, owner_headers: dict, event: Event, tmp_path: Path
):
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={
                "filename": "photo.jpg",
                "file_size_bytes": 4 * 1024 * 1024,  # 4 MB → 2 chunks
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
    client: AsyncClient, owner_headers: dict, event: Event, tmp_path: Path
):
    """A 1-byte file → 1 chunk; a 2MB+1-byte file → 2 chunks."""
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
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

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
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
    client: AsyncClient, owner_headers: dict, event: Event, tmp_path: Path
):
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads",
            headers=owner_headers,
            json={"filename": "video.mp4", "file_size_bytes": 1024, "content_hash": "h"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_initiate_upload_rejects_oversized_file(
    client: AsyncClient, owner_headers: dict, event: Event, tmp_path: Path
):
    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
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


# ---------------------------------------------------------------------------
# 2. Dedup: initiate same content_hash → 200 duplicate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_upload_dedup_existing_photo(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path
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

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
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
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """If an in-progress session with the same content_hash exists → 200 {status: resumable}."""
    existing_session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="inflight.jpg",
        file_size_bytes=5 * 1024 * 1024,
        content_hash="inflight-hash-456",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=3,
        received_chunks=[0, 1],
        status="in_progress",
    )
    db.add(existing_session)
    await db.commit()

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
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
    assert body["received_chunks"] == [0, 1]
    assert body["total_chunks"] == 3


# ---------------------------------------------------------------------------
# 3. Upload chunk → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_chunk_returns_200(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """Uploading a chunk to a valid session returns {chunk_index, received: true}."""
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
    )
    db.add(session)
    await db.commit()

    chunk_data = _fake_jpeg(CHUNK_SIZE)

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.put(
            f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/0",
            headers={**owner_headers, "Content-Type": "application/octet-stream"},
            content=chunk_data,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["chunk_index"] == 0
    assert body["received"] is True

    # Verify chunk file was written
    chunk_file = tmp_path / "tmp" / str(session.id) / "0.bin"
    assert chunk_file.exists()
    assert chunk_file.read_bytes() == chunk_data


@pytest.mark.asyncio
async def test_upload_chunk_idempotent(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """Uploading the same chunk twice is idempotent — second call returns 200 without error."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="test.jpg",
        file_size_bytes=CHUNK_SIZE * 2,
        content_hash="idempotent-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=2,
        received_chunks=[0],  # chunk 0 already received
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.put(
            f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/0",
            headers={**owner_headers, "Content-Type": "application/octet-stream"},
            content=b"some data",
        )

    assert resp.status_code == 200
    assert resp.json()["received"] is True


@pytest.mark.asyncio
async def test_upload_chunk_rejects_out_of_range(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
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
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.put(
            f"/api/v1/events/{event.id}/uploads/{session.id}/chunks/5",
            headers={**owner_headers, "Content-Type": "application/octet-stream"},
            content=b"data",
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Complete upload → 201 with photo_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_upload_returns_201(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """POST /complete assembles chunks and returns {photo_id}."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="final.jpg",
        file_size_bytes=len(_fake_jpeg(500)),
        content_hash="complete-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[0],
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    # Write the chunk file manually
    tmp_session_dir = tmp_path / "tmp" / str(session.id)
    tmp_session_dir.mkdir(parents=True)
    chunk_data = _fake_jpeg(500)
    (tmp_session_dir / "0.bin").write_bytes(chunk_data)

    with patch("app.routers.uploads.settings") as mock_settings, \
         patch("app.routers.uploads.process_photo"):
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "photo_id" in body
    uuid.UUID(body["photo_id"])  # assert parseable


@pytest.mark.asyncio
async def test_complete_upload_creates_photo_record(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """After /complete, a Photo row exists in the DB with the correct metadata."""
    from sqlalchemy import select

    content_hash = "complete-hash-002"
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="wedding.jpg",
        file_size_bytes=400,
        content_hash=content_hash,
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[0],
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    tmp_session_dir = tmp_path / "tmp" / str(session.id)
    tmp_session_dir.mkdir(parents=True)
    chunk_data = _fake_jpeg(400)
    (tmp_session_dir / "0.bin").write_bytes(chunk_data)

    with patch("app.routers.uploads.settings") as mock_settings, \
         patch("app.routers.uploads.process_photo"):
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
    photo_id = uuid.UUID(resp.json()["photo_id"])

    result = await db.execute(select(Photo).where(Photo.id == photo_id))
    photo = result.scalar_one_or_none()
    assert photo is not None
    assert photo.event_id == event.id
    assert photo.content_hash == content_hash
    assert photo.processing_status == "pending"
    assert photo.filename == "wedding.jpg"


@pytest.mark.asyncio
async def test_complete_upload_missing_chunks_returns_422(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """If not all chunks are received, /complete returns 422 with missing indices."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="incomplete.jpg",
        file_size_bytes=CHUNK_SIZE * 3,
        content_hash="incomplete-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=3,
        received_chunks=[0, 2],  # missing chunk 1
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 422
    assert "1" in resp.json()["detail"]  # missing chunk 1 mentioned in error


@pytest.mark.asyncio
async def test_complete_upload_rejects_invalid_image(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """If assembled file is not JPEG/PNG, /complete returns 422."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="fake.jpg",
        file_size_bytes=100,
        content_hash="invalid-image-hash",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[0],
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    tmp_session_dir = tmp_path / "tmp" / str(session.id)
    tmp_session_dir.mkdir(parents=True)
    # Write garbage data (not JPEG or PNG)
    (tmp_session_dir / "0.bin").write_bytes(b"this is not an image" + b"\x00" * 80)

    with patch("app.routers.uploads.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Resume — GET session → list received chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_returns_received_chunks(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, owner: User
):
    """GET /{session_id} returns the list of received chunk indices."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="resume.jpg",
        file_size_bytes=CHUNK_SIZE * 5,
        content_hash="resume-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=5,
        received_chunks=[0, 1, 3],
        status="in_progress",
    )
    db.add(session)
    await db.commit()

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
    )
    db.add(session)
    await db.commit()

    # Query with wrong event_id (using `event` not `other_event`)
    resp = await client.get(
        f"/api/v1/events/{event.id}/uploads/{session.id}",
        headers=owner_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. PNG support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_upload_accepts_png(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path, owner: User
):
    """A valid PNG-magic chunk should be accepted by /complete."""
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="photo.png",
        file_size_bytes=200,
        content_hash="png-hash-001",
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=1,
        received_chunks=[0],
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    tmp_session_dir = tmp_path / "tmp" / str(session.id)
    tmp_session_dir.mkdir(parents=True)
    (tmp_session_dir / "0.bin").write_bytes(_fake_png(200))

    with patch("app.routers.uploads.settings") as mock_settings, \
         patch("app.routers.uploads.process_photo"):
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.post(
            f"/api/v1/events/{event.id}/uploads/{session.id}/complete",
            json={},
            headers=owner_headers,
        )

    assert resp.status_code == 201
