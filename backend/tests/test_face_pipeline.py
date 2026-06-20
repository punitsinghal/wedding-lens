"""Tests for the AI face processing pipeline."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.event import Event
from app.models.photo import FaceRecord, Photo
from app.models.user import User
from app.services.auth import create_access_token, hash_password
from app.utils.crypto import decrypt_embedding, encrypt_embedding

# Import the TestSessionLocal so we can patch AsyncSessionLocal in services
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def patch_async_session_local():
    """Redirect all AsyncSessionLocal calls in services to the test SQLite session."""
    with patch("app.services.face_pipeline.AsyncSessionLocal", TestSessionLocal), \
         patch("app.services.retry.AsyncSessionLocal", TestSessionLocal):
        yield

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user(db):
    u = User(
        id=uuid.uuid4(),
        email="pipeline-user@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def event(db, user):
    ev = Event(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Pipeline Test Event",
        bride_name="Bride",
        groom_name="Groom",
        slug=f"pipeline-test-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest_asyncio.fixture
async def photo(db, event):
    p = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="test.jpg",
        storage_path=f"events/{event.id}/test.jpg",
        file_size=1024,
        processing_status="pending",
        processing_attempts=0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest.fixture
def photographer_token(user):
    return create_access_token(str(user.id))


@pytest.fixture
def auth_headers(photographer_token):
    return {"Authorization": f"Bearer {photographer_token}"}


# ---------------------------------------------------------------------------
# A. Crypto round-trip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip():
    embedding = np.random.rand(512).astype(np.float32)
    secret = "test-secret"
    enc = encrypt_embedding(embedding, secret)
    dec = decrypt_embedding(enc, secret)
    np.testing.assert_array_almost_equal(embedding, dec)


def test_encrypt_produces_different_nonces():
    embedding = np.ones(512, dtype=np.float32)
    secret = "test-secret"
    enc1 = encrypt_embedding(embedding, secret)
    enc2 = encrypt_embedding(embedding, secret)
    assert enc1 != enc2  # different nonces
    # 12 (nonce) + 2048 (payload) + 16 (GCM tag) = 2076
    assert len(enc1) == 2076


# ---------------------------------------------------------------------------
# B. Pipeline — zero faces
# ---------------------------------------------------------------------------


async def test_run_pipeline_zero_faces(db, photo, event, tmp_path):
    """When no faces are detected, photo is marked complete with face_count=0."""
    # Write a dummy image file so the path read doesn't fail
    img_dir = tmp_path / "events" / str(event.id)
    img_dir.mkdir(parents=True)
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake-image-bytes")

    # Update photo storage_path to point to tmp_path
    photo.storage_path = f"events/{event.id}/test.jpg"
    await db.commit()

    import app.services.face_pipeline as fp_module
    original_storage = fp_module.settings.STORAGE_PATH
    fp_module.settings.STORAGE_PATH = str(tmp_path)
    try:
        with patch("app.services.face_pipeline._detect_faces", return_value=[]) as mock_detect, \
             patch("app.services.qdrant.ensure_collection"), \
             patch("app.services.qdrant.upsert_face_vectors") as mock_upsert:
            from app.services.face_pipeline import _run_pipeline
            await _run_pipeline(photo.id, event.id)
    finally:
        fp_module.settings.STORAGE_PATH = original_storage

    # Refresh photo from DB
    await db.refresh(photo)
    assert photo.processing_status == "complete"
    assert photo.face_count == 0

    # No FaceRecord rows
    result = await db.execute(select(FaceRecord).where(FaceRecord.photo_id == photo.id))
    records = result.scalars().all()
    assert len(records) == 0

    mock_detect.assert_called_once()
    mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# C. Pipeline — multiple faces
# ---------------------------------------------------------------------------


async def test_run_pipeline_multiple_faces(db, photo, event, tmp_path):
    """When faces are detected, face_records are created and Qdrant is called."""
    img_dir = tmp_path / "events" / str(event.id)
    img_dir.mkdir(parents=True)
    (img_dir / "test.jpg").write_bytes(b"fake-image-bytes")

    face1 = {"bbox": [10, 20, 60, 80], "embedding": np.random.rand(512).astype(np.float32)}
    face2 = {"bbox": [100, 120, 70, 90], "embedding": np.random.rand(512).astype(np.float32)}
    fake_faces = [face1, face2]

    import app.services.face_pipeline as fp_module
    original_storage = fp_module.settings.STORAGE_PATH
    fp_module.settings.STORAGE_PATH = str(tmp_path)
    try:
        with patch("app.services.face_pipeline._detect_faces", return_value=fake_faces), \
             patch("app.services.qdrant.ensure_collection"), \
             patch("app.services.qdrant.upsert_face_vectors") as mock_upsert:
            from app.services.face_pipeline import _run_pipeline
            await _run_pipeline(photo.id, event.id)
    finally:
        fp_module.settings.STORAGE_PATH = original_storage

    await db.refresh(photo)
    assert photo.processing_status == "complete"
    assert photo.face_count == 2

    result = await db.execute(select(FaceRecord).where(FaceRecord.photo_id == photo.id))
    records = result.scalars().all()
    assert len(records) == 2

    mock_upsert.assert_called_once()
    call_args = mock_upsert.call_args
    assert call_args[0][0] == event.id
    assert len(call_args[0][1]) == 2


# ---------------------------------------------------------------------------
# D. Idempotency — already complete
# ---------------------------------------------------------------------------


async def test_process_photo_skips_complete(db, event):
    """process_photo exits immediately if photo is already complete."""
    completed_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="done.jpg",
        storage_path="events/done.jpg",
        file_size=512,
        processing_status="complete",
        processing_attempts=1,
        face_count=0,
    )
    db.add(completed_photo)
    await db.commit()

    with patch("app.services.face_pipeline._run_pipeline") as mock_run:
        from app.services.face_pipeline import process_photo
        await process_photo(completed_photo.id, event.id)

    mock_run.assert_not_called()

    await db.refresh(completed_photo)
    assert completed_photo.processing_status == "complete"


# ---------------------------------------------------------------------------
# E. Idempotency — already processing (concurrent)
# ---------------------------------------------------------------------------


async def test_process_photo_skips_in_processing(db, event):
    """process_photo exits immediately if photo is already being processed."""
    processing_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="inprog.jpg",
        storage_path="events/inprog.jpg",
        file_size=512,
        processing_status="processing",
        processing_attempts=1,
        last_processed_at=datetime.now(timezone.utc),
    )
    db.add(processing_photo)
    await db.commit()

    with patch("app.services.face_pipeline._run_pipeline") as mock_run:
        from app.services.face_pipeline import process_photo
        await process_photo(processing_photo.id, event.id)

    mock_run.assert_not_called()

    result = await db.execute(
        select(FaceRecord).where(FaceRecord.photo_id == processing_photo.id)
    )
    assert len(result.scalars().all()) == 0


# ---------------------------------------------------------------------------
# F. Failure → failed status (attempts < 5)
# ---------------------------------------------------------------------------


async def test_run_pipeline_error_sets_failed(db, photo, event, tmp_path):
    """When an error occurs with attempts < 5, status becomes 'failed'."""
    img_dir = tmp_path / "events" / str(event.id)
    img_dir.mkdir(parents=True)
    (img_dir / "test.jpg").write_bytes(b"fake")

    # Manually set processing_attempts to 1 to simulate gate passage
    photo.processing_attempts = 1
    await db.commit()

    import app.services.face_pipeline as fp_module
    original_storage = fp_module.settings.STORAGE_PATH
    fp_module.settings.STORAGE_PATH = str(tmp_path)
    try:
        with patch("app.services.face_pipeline._detect_faces", side_effect=RuntimeError("boom")):
            from app.services.face_pipeline import _run_pipeline
            await _run_pipeline(photo.id, event.id)
    finally:
        fp_module.settings.STORAGE_PATH = original_storage

    await db.refresh(photo)
    assert photo.processing_status == "failed"


# ---------------------------------------------------------------------------
# G. Failure → error status (attempts >= 5)
# ---------------------------------------------------------------------------


async def test_run_pipeline_error_sets_error_at_max_attempts(db, event, tmp_path):
    """When attempts >= 5, error status is set instead of failed."""
    img_dir = tmp_path / "events" / str(event.id)
    img_dir.mkdir(parents=True)
    (img_dir / "test.jpg").write_bytes(b"fake")

    exhausted_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="test.jpg",
        storage_path=f"events/{event.id}/test.jpg",
        file_size=512,
        processing_status="processing",
        processing_attempts=5,
        last_processed_at=datetime.now(timezone.utc),
    )
    db.add(exhausted_photo)
    await db.commit()

    import app.services.face_pipeline as fp_module
    original_storage = fp_module.settings.STORAGE_PATH
    fp_module.settings.STORAGE_PATH = str(tmp_path)
    try:
        with patch("app.services.face_pipeline._detect_faces", side_effect=RuntimeError("boom")):
            from app.services.face_pipeline import _run_pipeline
            await _run_pipeline(exhausted_photo.id, event.id)
    finally:
        fp_module.settings.STORAGE_PATH = original_storage

    await db.refresh(exhausted_photo)
    assert exhausted_photo.processing_status == "error"


# ---------------------------------------------------------------------------
# H. Retry job — resets stuck jobs
# ---------------------------------------------------------------------------


async def test_reset_stuck_jobs(db, event):
    """_reset_stuck_jobs moves processing photos older than 15 min back to pending."""
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    stuck_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="stuck.jpg",
        storage_path="events/stuck.jpg",
        file_size=512,
        processing_status="processing",
        processing_attempts=1,
        last_processed_at=old_time,
    )
    db.add(stuck_photo)
    await db.commit()

    from app.services.retry import _reset_stuck_jobs
    await _reset_stuck_jobs()

    await db.refresh(stuck_photo)
    assert stuck_photo.processing_status == "pending"


# ---------------------------------------------------------------------------
# I. Retry job — doesn't reset recent processing jobs
# ---------------------------------------------------------------------------


async def test_reset_stuck_jobs_ignores_recent(db, event):
    """_reset_stuck_jobs does not touch photos processed recently."""
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="recent.jpg",
        storage_path="events/recent.jpg",
        file_size=512,
        processing_status="processing",
        processing_attempts=1,
        last_processed_at=recent_time,
    )
    db.add(recent_photo)
    await db.commit()

    from app.services.retry import _reset_stuck_jobs
    await _reset_stuck_jobs()

    await db.refresh(recent_photo)
    assert recent_photo.processing_status == "processing"


# ---------------------------------------------------------------------------
# J. Status endpoint — auth required (no token → 401)
# ---------------------------------------------------------------------------


async def test_status_endpoint_requires_auth(client, event):
    # FastAPI HTTPBearer returns 403 when no Authorization header is provided
    resp = await client.get(f"/api/v1/events/{event.id}/face-processing/status")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# K. Status endpoint — correct counts
# ---------------------------------------------------------------------------


async def test_status_endpoint_counts(client, db, user, event, auth_headers):
    """Status endpoint returns correct per-status counts."""
    for i, st in enumerate(["complete", "complete", "failed"]):
        db.add(Photo(
            id=uuid.uuid4(),
            event_id=event.id,
            filename=f"photo_{i}.jpg",
            storage_path=f"events/{event.id}/photo_{i}.jpg",
            file_size=512,
            processing_status=st,
        ))
    await db.commit()

    resp = await client.get(
        f"/api/v1/events/{event.id}/face-processing/status",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_photos"] == 3
    assert data["by_status"]["complete"] == 2
    assert data["by_status"]["failed"] == 1
    assert data["by_status"]["pending"] == 0


# ---------------------------------------------------------------------------
# L. Status endpoint — 404 for wrong owner
# ---------------------------------------------------------------------------


async def test_status_endpoint_wrong_owner(client, db):
    """User A's token cannot see User B's event."""
    user_a = User(
        id=uuid.uuid4(),
        email="user-a@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    user_b = User(
        id=uuid.uuid4(),
        email="user-b@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add_all([user_a, user_b])
    await db.commit()

    event_b = Event(
        id=uuid.uuid4(),
        owner_id=user_b.id,
        name="User B's Event",
        bride_name="Bride",
        groom_name="Groom",
        slug=f"user-b-event-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(event_b)
    await db.commit()

    token_a = create_access_token(str(user_a.id))
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp = await client.get(
        f"/api/v1/events/{event_b.id}/face-processing/status",
        headers=headers_a,
    )
    assert resp.status_code == 404
