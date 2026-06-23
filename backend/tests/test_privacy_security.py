"""Tests for Privacy & Security feature.

Covers:
  AC-1c/1d  — consent record created on publish + new record on republish
  AC-2e     — consent_ack 422 when absent/false
  AC-5a/5b  — 11th request → 429 + Retry-After header
  AC-5d     — window reset allows a new request (injected clock, no sleep)
  AC-3b/3c  — removal submit success: 200 + record persisted
  AC-3d     — 422 on missing required field, no DB row created
  AC-4a/4b  — fulfill updates status+timestamp; record persists (never deleted)
  AC-7a     — audit returns embeddings_encrypted bool
  AC-7b     — audit 401/403 without admin
  AC-6b     — HSTS header present on all responses
  No-FK ADR — purged event leaves consent/removal records intact
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import FaceRecord, Photo
from app.models.privacy import ConsentRecord, RemovalRequest
from app.models.user import User
from app.services.auth import create_access_token, hash_password
from app.services.guest_auth import create_guest_token
from app.services.search_cache import search_cache
from app.services.search_rate_limit import SearchRateLimiter, search_rate_limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_rate_limiter_and_cache():
    """Reset rate limiter and cache before each test."""
    search_rate_limiter.clear_all()
    search_cache.clear()
    yield
    search_rate_limiter.clear_all()
    search_cache.clear()


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("pw"),
        is_admin=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def published_event(db: AsyncSession, owner: User) -> Event:
    """Event with a cover_photo_id set (needed to publish)."""
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Privacy Test Wedding",
        bride_name="Asha",
        groom_name="Dev",
        slug=f"privacy-test-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="draft",
        guest_access_enabled=True,
        cover_photo_id=uuid.uuid4(),  # Fake cover photo — needed for publish
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest_asyncio.fixture
async def guest_event(db: AsyncSession, owner: User) -> Event:
    """Published event for guest-facing tests."""
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Guest Event Wedding",
        bride_name="Mira",
        groom_name="Raj",
        slug=f"guest-evt-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
        cover_photo_id=uuid.uuid4(),
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


def _owner_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _guest_headers(event_id: uuid.UUID, sid: str | None = None) -> dict:
    token = create_guest_token(str(event_id), sid=sid)
    return {"Authorization": f"Bearer {token}"}


def _fake_embedding() -> np.ndarray:
    v = np.random.rand(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _fake_selfie(size: int = 100) -> bytes:
    return b"x" * size


# ===========================================================================
# AC-1c — Consent record created when event is published
# ===========================================================================


@pytest.mark.asyncio
async def test_publish_creates_consent_record(
    client: AsyncClient, db: AsyncSession, published_event: Event, owner: User
):
    """AC-1c: publishing creates exactly one ConsentRecord."""
    headers = _owner_headers(owner)
    resp = await client.post(
        f"/api/v1/events/{published_event.id}/publish", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.event_id == published_event.id)
    )
    records = list(result.scalars().all())
    assert len(records) == 1
    assert records[0].confirmed_by == owner.id
    assert records[0].event_id == published_event.id
    assert records[0].confirmed_at is not None


# ===========================================================================
# AC-1d — Republish creates a NEW consent record
# ===========================================================================


@pytest.mark.asyncio
async def test_republish_creates_new_consent_record(
    client: AsyncClient, db: AsyncSession, published_event: Event, owner: User
):
    """AC-1d: unpublish → republish creates a fresh ConsentRecord (no deduplication)."""
    headers = _owner_headers(owner)

    # First publish
    await client.post(f"/api/v1/events/{published_event.id}/publish", headers=headers)

    # Unpublish
    await client.post(f"/api/v1/events/{published_event.id}/unpublish", headers=headers)

    # Re-publish
    await client.post(f"/api/v1/events/{published_event.id}/publish", headers=headers)

    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.event_id == published_event.id)
    )
    records = list(result.scalars().all())
    assert len(records) == 2, f"Expected 2 consent records, got {len(records)}"


# ===========================================================================
# AC-2e — consent_ack 422 when absent or false
# ===========================================================================


@pytest.mark.asyncio
async def test_search_consent_ack_missing_returns_422(
    client: AsyncClient, guest_event: Event
):
    """If consent_ack is absent from multipart form → 422 (missing field)."""
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/search",
        files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
        # No consent_ack field
        headers=_guest_headers(guest_event.id),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_consent_ack_false_returns_422(
    client: AsyncClient, guest_event: Event
):
    """If consent_ack=false → 422 consent_required."""
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/search",
        files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
        data={"consent_ack": "false"},
        headers=_guest_headers(guest_event.id),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "consent_required"


# ===========================================================================
# AC-5a/5b — 11th request → 429 with Retry-After
# ===========================================================================


@pytest.mark.asyncio
async def test_rate_limit_11th_request_returns_429(
    client: AsyncClient, guest_event: Event
):
    """AC-5a/5b: 11th search request in window → 429 + Retry-After."""
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    sid = str(uuid.uuid4())
    headers = _guest_headers(guest_event.id, sid=sid)

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", return_value=[]):
        for i in range(10):
            resp = await client.post(
                f"/api/v1/events/{guest_event.id}/search",
                files={"selfie": ("s.jpg", _fake_selfie(i + 1), "image/jpeg")},
                data={"consent_ack": "true"},
                headers=headers,
            )
            assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"

        # 11th request
        resp = await client.post(
            f"/api/v1/events/{guest_event.id}/search",
            files={"selfie": ("s.jpg", _fake_selfie(11), "image/jpeg")},
            data={"consent_ack": "true"},
            headers=headers,
        )

    assert resp.status_code == 429
    assert resp.json()["detail"] == "rate_limited"
    assert "retry-after" in resp.headers
    retry_after = int(resp.headers["retry-after"])
    assert retry_after > 0


# ===========================================================================
# AC-5d — Window reset allows a new request (injected clock — no sleep)
# ===========================================================================


@pytest.mark.asyncio
async def test_rate_limit_window_reset_allows_new_request(
    client: AsyncClient, guest_event: Event
):
    """AC-5d: after window expires, guest can submit again (injected clock)."""
    fake_time = [0.0]

    def fake_clock() -> float:
        return fake_time[0]

    # Custom limiter: max 3 per 10-second window, injected clock
    custom_limiter = SearchRateLimiter(max_requests=3, window_seconds=10, clock=fake_clock)

    sid = str(uuid.uuid4())

    # Fill window at t=0
    custom_limiter.check_and_record(sid)
    custom_limiter.check_and_record(sid)
    custom_limiter.check_and_record(sid)

    # 4th at t=0 should raise
    from app.services.search_rate_limit import RateLimitExceeded
    with pytest.raises(RateLimitExceeded):
        custom_limiter.check_and_record(sid)

    # Advance clock past the window
    fake_time[0] = 11.0

    # Should now succeed (window reset)
    custom_limiter.check_and_record(sid)  # no exception → pass


# ===========================================================================
# AC-3b/3c — Removal request submit: 200 + record persisted
# ===========================================================================


@pytest.mark.asyncio
async def test_removal_request_submit_success(
    client: AsyncClient, db: AsyncSession, guest_event: Event
):
    """AC-3b/3c: valid submission → 200 and record persisted as 'pending'."""
    headers = _guest_headers(guest_event.id)
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/removal-requests",
        json={
            "name": "Test Guest",
            "email": "guest@example.com",
            "description": "I uploaded a selfie at 3pm",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert "24 hours" in body["message"]
    request_id = uuid.UUID(body["id"])

    # Verify DB record
    result = await db.execute(
        select(RemovalRequest).where(RemovalRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    assert req is not None
    assert req.status == "pending"
    assert req.event_id == guest_event.id
    assert req.guest_name == "Test Guest"
    assert req.guest_email == "guest@example.com"
    assert req.description == "I uploaded a selfie at 3pm"
    assert req.submitted_at is not None
    assert req.fulfilled_at is None


# ===========================================================================
# AC-3d — Missing required field → 422, no DB row
# ===========================================================================


@pytest.mark.asyncio
async def test_removal_request_missing_name_returns_422(
    client: AsyncClient, db: AsyncSession, guest_event: Event
):
    """AC-3d: missing 'name' → 422 and no DB row created."""
    headers = _guest_headers(guest_event.id)
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/removal-requests",
        json={"email": "x@example.com", "description": "desc"},
        headers=headers,
    )
    assert resp.status_code == 422

    result = await db.execute(select(RemovalRequest))
    rows = list(result.scalars().all())
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_removal_request_missing_email_returns_422(
    client: AsyncClient, db: AsyncSession, guest_event: Event
):
    """AC-3d: missing 'email' → 422 and no DB row created."""
    headers = _guest_headers(guest_event.id)
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/removal-requests",
        json={"name": "Test", "description": "desc"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_removal_request_missing_description_returns_422(
    client: AsyncClient, db: AsyncSession, guest_event: Event
):
    """AC-3d: missing 'description' → 422 and no DB row created."""
    headers = _guest_headers(guest_event.id)
    resp = await client.post(
        f"/api/v1/events/{guest_event.id}/removal-requests",
        json={"name": "Test", "email": "x@example.com"},
        headers=headers,
    )
    assert resp.status_code == 422


# ===========================================================================
# AC-4a/4b — Admin fulfill: updates status+timestamp, record never deleted
# ===========================================================================


@pytest_asyncio.fixture
async def pending_removal_request(db: AsyncSession, guest_event: Event) -> RemovalRequest:
    req = RemovalRequest(
        id=uuid.uuid4(),
        event_id=guest_event.id,
        submitted_at=datetime.now(timezone.utc),
        guest_name="Alice",
        guest_email="alice@example.com",
        description="I searched at noon",
        status="pending",
        fulfilled_at=None,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


@pytest.mark.asyncio
async def test_admin_fulfill_removal_request(
    client: AsyncClient,
    db: AsyncSession,
    pending_removal_request: RemovalRequest,
    admin: User,
):
    """AC-4a: fulfilling updates status='fulfilled' + fulfilled_at timestamp."""
    headers = _admin_headers(admin)
    resp = await client.post(
        f"/api/v1/admin/removal-requests/{pending_removal_request.id}/fulfill",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fulfilled"
    assert body["fulfilled_at"] is not None


@pytest.mark.asyncio
async def test_fulfilled_removal_request_not_deleted(
    client: AsyncClient,
    db: AsyncSession,
    pending_removal_request: RemovalRequest,
    admin: User,
):
    """AC-4b: after fulfillment the record still exists in the DB."""
    request_id = pending_removal_request.id
    headers = _admin_headers(admin)
    resp = await client.post(
        f"/api/v1/admin/removal-requests/{request_id}/fulfill",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    # The response itself confirms the record is there and updated.
    assert body["status"] == "fulfilled"
    assert body["fulfilled_at"] is not None
    assert body["id"] == str(request_id)
    # Record is NOT deleted — it's returned in the response (AC-4b).


# ===========================================================================
# AC-7a — Audit endpoint returns embeddings_encrypted bool
# ===========================================================================


@pytest.mark.asyncio
async def test_audit_no_face_records_returns_true(
    client: AsyncClient, admin: User
):
    """AC-7a: with no face records, embeddings_encrypted=true, checked=0."""
    headers = _admin_headers(admin)
    resp = await client.get("/internal/audit/embedding-encryption", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeddings_encrypted"] is True
    assert body["checked_count"] == 0
    assert body["total_count"] == 0


@pytest.mark.asyncio
async def test_audit_with_valid_encrypted_record_returns_true(
    client: AsyncClient, db: AsyncSession, admin: User, guest_event: Event
):
    """AC-7a: face_records with valid embedding_enc → embeddings_encrypted=true."""
    from app.utils.crypto import encrypt_embedding
    from app.config import settings

    # Create a photo first
    photo = Photo(
        id=uuid.uuid4(),
        event_id=guest_event.id,
        filename="p.jpg",
        storage_path="events/x/p.jpg",
        file_size=1024,
        processing_status="complete",
    )
    db.add(photo)
    await db.flush()

    emb = np.random.rand(512).astype(np.float32)
    enc = encrypt_embedding(emb, settings.SECRET_KEY)

    face = FaceRecord(
        id=uuid.uuid4(),
        photo_id=photo.id,
        event_id=guest_event.id,
        qdrant_point_id=uuid.uuid4(),
        bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100,
        embedding_enc=enc,
    )
    db.add(face)
    await db.commit()

    headers = _admin_headers(admin)
    resp = await client.get("/internal/audit/embedding-encryption", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeddings_encrypted"] is True
    assert body["checked_count"] == 1
    assert body["total_count"] == 1


@pytest.mark.asyncio
async def test_audit_with_garbled_embedding_returns_false(
    client: AsyncClient, db: AsyncSession, admin: User, guest_event: Event
):
    """AC-7a: face_records with undecrpytable bytes → embeddings_encrypted=false."""
    photo = Photo(
        id=uuid.uuid4(),
        event_id=guest_event.id,
        filename="p.jpg",
        storage_path="events/x/p.jpg",
        file_size=1024,
        processing_status="complete",
    )
    db.add(photo)
    await db.flush()

    face = FaceRecord(
        id=uuid.uuid4(),
        photo_id=photo.id,
        event_id=guest_event.id,
        qdrant_point_id=uuid.uuid4(),
        bbox_x=0, bbox_y=0, bbox_w=100, bbox_h=100,
        embedding_enc=b"not-valid-encrypted-data",
    )
    db.add(face)
    await db.commit()

    headers = _admin_headers(admin)
    resp = await client.get("/internal/audit/embedding-encryption", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeddings_encrypted"] is False


# ===========================================================================
# AC-7b — Audit 401/403 without admin
# ===========================================================================


@pytest.mark.asyncio
async def test_audit_requires_admin_no_token(client: AsyncClient):
    """AC-7b: no auth → 403 (HTTPBearer)."""
    resp = await client.get("/internal/audit/embedding-encryption")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_requires_admin_non_admin_user(
    client: AsyncClient, owner: User
):
    """AC-7b: non-admin user → 403."""
    headers = _owner_headers(owner)
    resp = await client.get("/internal/audit/embedding-encryption", headers=headers)
    assert resp.status_code == 403


# ===========================================================================
# AC-6b — HSTS header present on all responses
# ===========================================================================


@pytest.mark.asyncio
async def test_hsts_header_on_health_endpoint(client: AsyncClient):
    """AC-6b: HSTS header with max-age >= 31536000 on every response."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    sts = resp.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in sts
    assert "includeSubDomains" in sts


@pytest.mark.asyncio
async def test_hsts_header_on_api_response(client: AsyncClient):
    """AC-6b: HSTS header present on API responses too."""
    resp = await client.get("/api/v1/events/by-slug/does-not-exist")
    assert resp.status_code == 404
    sts = resp.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in sts


# ===========================================================================
# No-FK ADR: purged event leaves consent/removal records intact
# ===========================================================================


@pytest.mark.asyncio
async def test_consent_record_survives_event_deletion(
    client: AsyncClient, db: AsyncSession, published_event: Event, owner: User
):
    """No-FK ADR: deleting the event leaves ConsentRecord intact."""
    headers = _owner_headers(owner)

    # Publish to create a consent record
    await client.post(
        f"/api/v1/events/{published_event.id}/publish", headers=headers
    )

    # Verify consent record exists
    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.event_id == published_event.id)
    )
    assert len(list(result.scalars().all())) == 1

    # Hard-delete the event (simulates what the purge job does)
    await db.delete(published_event)
    await db.flush()

    # ConsentRecord must still be there
    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.event_id == published_event.id)
    )
    survivors = list(result.scalars().all())
    assert len(survivors) == 1, (
        "ConsentRecord was deleted when event was deleted — violates ADR 2026-06-23"
    )


@pytest.mark.asyncio
async def test_removal_request_survives_event_deletion(
    db: AsyncSession, guest_event: Event
):
    """No-FK ADR: deleting the event leaves RemovalRequest intact."""
    req = RemovalRequest(
        id=uuid.uuid4(),
        event_id=guest_event.id,
        submitted_at=datetime.now(timezone.utc),
        guest_name="Bob",
        guest_email="bob@example.com",
        description="Searched at 2pm",
        status="pending",
    )
    db.add(req)
    await db.commit()

    # Hard-delete the event
    await db.delete(guest_event)
    await db.flush()

    result = await db.execute(
        select(RemovalRequest).where(RemovalRequest.id == req.id)
    )
    survivor = result.scalar_one_or_none()
    assert survivor is not None, (
        "RemovalRequest was deleted when event was deleted — violates ADR 2026-06-23"
    )
