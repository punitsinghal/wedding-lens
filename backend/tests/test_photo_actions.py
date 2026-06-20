"""Photo actions endpoint tests."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.favourites_store import favourites_store
from app.services.guest_auth import create_guest_token, create_share_token, decode_share_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_event(db: AsyncSession, owner: User) -> Event:
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"test-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def _make_photo(
    db: AsyncSession,
    event: Event,
    storage_path: str | None = None,
    filename: str = "photo.jpg",
    thumbnail_path: str | None = None,
) -> Photo:
    sp = storage_path or f"events/{event.id}/{uuid.uuid4()}.jpg"
    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename=filename,
        storage_path=sp,
        file_size=1024,
        processing_status="complete",
    )
    if thumbnail_path is not None:
        photo.thumbnail_path = thumbnail_path
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


def _guest_headers(event_id: uuid.UUID, sid: str | None = None) -> dict:
    token = create_guest_token(str(event_id), sid=sid)
    return {"Authorization": f"Bearer {token}"}


def _guest_sid(event_id: uuid.UUID) -> tuple[dict, str]:
    """Returns (headers, sid) for a stable session."""
    sid = str(uuid.uuid4())
    headers = _guest_headers(event_id, sid=sid)
    return headers, sid


# ---------------------------------------------------------------------------
# Autouse fixture: clear favourites store between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_favourites():
    favourites_store.clear()
    yield
    favourites_store.clear()


# ---------------------------------------------------------------------------
# Test 1: bulk zip — cross-event photo rejected with 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_zip_rejects_cross_event_photo(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event_a = await _make_event(db, regular_user)
    event_b = await _make_event(db, regular_user)
    photo_b = await _make_photo(db, event_b)

    resp = await client.post(
        f"/api/v1/events/{event_a.id}/photos/zip",
        json={"photo_ids": [str(photo_b.id)]},
        headers=_guest_headers(event_a.id),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "photo_not_in_event"


# ---------------------------------------------------------------------------
# Test 2: bulk zip — empty photo_ids returns 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_zip_empty_ids_returns_400(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/zip",
        json={"photo_ids": []},
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "photo_ids_required"


# ---------------------------------------------------------------------------
# Test 3: share token expired → decode raises 410
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_token_expired_returns_410():
    from fastapi import HTTPException

    photo_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # Create a token that already expired
    now = datetime.now(timezone.utc)
    payload = {
        "type": "share",
        "sub": event_id,
        "photo_id": photo_id,
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(hours=73),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        decode_share_token(token)

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail == "link_expired"


# ---------------------------------------------------------------------------
# Test 4: share token bad signature → decode raises 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_token_invalid_returns_403():
    from fastapi import HTTPException

    photo_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    payload = {
        "type": "share",
        "sub": event_id,
        "photo_id": photo_id,
        "exp": now + timedelta(hours=72),
        "iat": now,
    }
    bad_token = jwt.encode(payload, "wrong-secret-key", algorithm=settings.ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        decode_share_token(bad_token)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "invalid_share_token"


# ---------------------------------------------------------------------------
# Test 5: guest token passed to decode_share_token → 403 (wrong type)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_token_wrong_type_returns_403():
    from fastapi import HTTPException

    event_id = str(uuid.uuid4())
    guest_token = create_guest_token(event_id)

    with pytest.raises(HTTPException) as exc_info:
        decode_share_token(guest_token)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "invalid_share_token"


# ---------------------------------------------------------------------------
# Test 6: favourites add → list → delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_favourites_add_remove_list(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)
    headers, _sid = _guest_sid(event.id)

    # Initially empty
    resp = await client.get(f"/api/v1/events/{event.id}/favourites", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["photos"] == []

    # Add favourite
    resp = await client.put(
        f"/api/v1/events/{event.id}/favourites/{photo.id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # List returns the photo
    resp = await client.get(f"/api/v1/events/{event.id}/favourites", headers=headers)
    assert resp.status_code == 200
    photos = resp.json()["photos"]
    assert len(photos) == 1
    assert photos[0]["photo_id"] == str(photo.id)

    # Remove favourite
    resp = await client.delete(
        f"/api/v1/events/{event.id}/favourites/{photo.id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # Empty again
    resp = await client.get(f"/api/v1/events/{event.id}/favourites", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["photos"] == []


# ---------------------------------------------------------------------------
# Test 7: favourites zip with no favourites → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_favourites_zip_empty_returns_400(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)

    resp = await client.post(
        f"/api/v1/events/{event.id}/favourites/zip",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "no_favourites"


# ---------------------------------------------------------------------------
# Test 8: two different sids have independent favourites
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_favourites_separate_sessions(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo_a = await _make_photo(db, event, filename="a.jpg")
    photo_b = await _make_photo(db, event, filename="b.jpg")

    headers_a, _sid_a = _guest_sid(event.id)
    headers_b, _sid_b = _guest_sid(event.id)

    # Session A adds photo_a
    await client.put(
        f"/api/v1/events/{event.id}/favourites/{photo_a.id}",
        headers=headers_a,
    )

    # Session B adds photo_b
    await client.put(
        f"/api/v1/events/{event.id}/favourites/{photo_b.id}",
        headers=headers_b,
    )

    # Session A sees only photo_a
    resp_a = await client.get(f"/api/v1/events/{event.id}/favourites", headers=headers_a)
    ids_a = {p["photo_id"] for p in resp_a.json()["photos"]}
    assert ids_a == {str(photo_a.id)}

    # Session B sees only photo_b
    resp_b = await client.get(f"/api/v1/events/{event.id}/favourites", headers=headers_b)
    ids_b = {p["photo_id"] for p in resp_b.json()["photos"]}
    assert ids_b == {str(photo_b.id)}


# ---------------------------------------------------------------------------
# Test 9: share endpoint returns share_url and expires_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_share_link(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/{photo.id}/share",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "share_url" in body
    assert "/share/" in body["share_url"]
    assert "expires_at" in body


# ---------------------------------------------------------------------------
# Test 10: GET /share/{token} resolves a valid share token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_share_token_valid(client: AsyncClient):
    photo_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    token = create_share_token(photo_id, event_id)

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["photo_id"] == photo_id
    assert body["event_id"] == event_id


# ---------------------------------------------------------------------------
# Test 11: GET /share/{token} returns 410 for expired token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_share_token_expired(client: AsyncClient):
    photo_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    payload = {
        "type": "share",
        "sub": event_id,
        "photo_id": photo_id,
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(hours=73),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    resp = await client.get(f"/api/v1/share/{token}")
    assert resp.status_code == 410
    assert resp.json()["detail"] == "link_expired"


# ---------------------------------------------------------------------------
# Test 12: bulk zip succeeds and returns ZIP bytes for valid photos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_zip_valid_photos(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)

    # Create a real file on disk
    storage_dir = Path(os.environ["STORAGE_PATH"]) / f"events/{event.id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    photo_filename = f"{uuid.uuid4()}.jpg"
    storage_path = f"events/{event.id}/{photo_filename}"
    (storage_dir / photo_filename).write_bytes(b"fake-photo-data")

    photo = await _make_photo(db, event, storage_path=storage_path, filename="myphoto.jpg")

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/zip",
        json={"photo_ids": [str(photo.id)]},
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    # ZIP magic bytes: PK\x03\x04
    assert resp.content[:2] == b"PK"
