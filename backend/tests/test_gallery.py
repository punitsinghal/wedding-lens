"""Gallery endpoint tests."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.auth import create_access_token
from app.services.guest_auth import create_guest_token


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


async def _make_album(db: AsyncSession, event: Event, category: str) -> Album:
    album = Album(
        id=uuid.uuid4(),
        event_id=event.id,
        name=category,
        ceremony_category=category,
    )
    db.add(album)
    await db.commit()
    await db.refresh(album)
    return album


async def _make_photo(
    db: AsyncSession,
    event: Event,
    album: Album | None = None,
    download_count: int = 0,
    is_photographer_choice: bool = False,
    thumbnail_path: str | None = None,
) -> Photo:
    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        album_id=album.id if album else None,
        filename="test.jpg",
        storage_path=f"events/{event.id}/{uuid.uuid4()}.jpg",
        file_size=1024,
        processing_status="complete",
        download_count=download_count,
        is_photographer_choice=is_photographer_choice,
        thumbnail_path=thumbnail_path,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


def _guest_headers(event_id: uuid.UUID) -> dict:
    token = create_guest_token(str(event_id))
    return {"Authorization": f"Bearer {token}"}


def _owner_headers(user: User) -> dict:
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1: GET /gallery returns 50 photos sorted by created_at DESC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_list_default_sort_latest(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    # Create 3 photos
    for _ in range(3):
        await _make_photo(db, event)

    resp = await client.get(
        f"/api/v1/events/{event.id}/gallery",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["photos"]) == 3
    # Verify sorted descending by created_at
    times = [p["created_at"] for p in body["photos"]]
    assert times == sorted(times, reverse=True)


# ---------------------------------------------------------------------------
# Test 2: GET /gallery?album=Sangeet returns only Sangeet photos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_filter_by_album(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    sangeet_album = await _make_album(db, event, "Sangeet")
    # Create 2 Sangeet photos and 1 unallocated photo
    await _make_photo(db, event, album=sangeet_album)
    await _make_photo(db, event, album=sangeet_album)
    await _make_photo(db, event, album=None)

    resp = await client.get(
        f"/api/v1/events/{event.id}/gallery?album=Sangeet",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["photos"]) == 2


# ---------------------------------------------------------------------------
# Test 3: GET /gallery?sort=popular returns photos by download_count DESC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_sort_popular(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    await _make_photo(db, event, download_count=5)
    await _make_photo(db, event, download_count=100)
    await _make_photo(db, event, download_count=10)

    resp = await client.get(
        f"/api/v1/events/{event.id}/gallery?sort=popular",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    body = resp.json()
    counts = [p["download_count"] for p in body["photos"]]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == 100


# ---------------------------------------------------------------------------
# Test 4: GET /gallery?sort=photographer-choice returns flagged photos first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_sort_photographer_choice(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    await _make_photo(db, event, is_photographer_choice=False)
    await _make_photo(db, event, is_photographer_choice=True)
    await _make_photo(db, event, is_photographer_choice=False)

    resp = await client.get(
        f"/api/v1/events/{event.id}/gallery?sort=photographer-choice",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    body = resp.json()
    photos = body["photos"]
    assert len(photos) == 3
    # First photo must be the flagged one
    assert photos[0]["is_photographer_choice"] is True
    # Rest must be unflagged
    assert all(not p["is_photographer_choice"] for p in photos[1:])


# ---------------------------------------------------------------------------
# Test 5: GET /gallery/albums returns All tab + tabs for categories present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_albums_tabs(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    sangeet_album = await _make_album(db, event, "Sangeet")
    ceremony_album = await _make_album(db, event, "Ceremony")
    # Add photos: 2 Sangeet, 1 Ceremony, 1 unallocated
    await _make_photo(db, event, album=sangeet_album)
    await _make_photo(db, event, album=sangeet_album)
    await _make_photo(db, event, album=ceremony_album)
    await _make_photo(db, event, album=None)

    resp = await client.get(
        f"/api/v1/events/{event.id}/gallery/albums",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    tabs = resp.json()

    # All tab first
    assert tabs[0]["ceremony_category"] is None
    assert tabs[0]["label"] == "All"
    assert tabs[0]["photo_count"] == 4

    labels = [t["label"] for t in tabs]
    # Ceremony comes before Sangeet in category order
    assert "Ceremony" in labels
    assert "Sangeet" in labels
    assert labels.index("Ceremony") < labels.index("Sangeet")

    # No zero-count tabs
    for tab in tabs:
        assert tab["photo_count"] > 0

    # Only All, Ceremony, Sangeet — no Mehendi, Haldi etc.
    assert len(tabs) == 3


# ---------------------------------------------------------------------------
# Test 6: PATCH photographer-choice with owner JWT → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_photographer_choice_owner_can_toggle(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event, is_photographer_choice=False)

    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{photo.id}/photographer-choice",
        json={"is_photographer_choice": True},
        headers=_owner_headers(regular_user),
    )
    assert resp.status_code == 200
    assert resp.json()["is_photographer_choice"] is True


# ---------------------------------------------------------------------------
# Test 7: PATCH photographer-choice with guest token → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_photographer_choice_guest_gets_403(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{photo.id}/photographer-choice",
        json={"is_photographer_choice": True},
        headers=_guest_headers(event.id),
    )
    # Guest token is not a valid owner JWT → 401 (bearer scheme requires owner JWT)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 8: GET /photos/{id}/download increments download_count by 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_increments_count(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    import os
    from pathlib import Path

    event = await _make_event(db, regular_user)

    # Create a real file on disk so FileResponse doesn't 404
    storage_dir = Path(os.environ["STORAGE_PATH"]) / f"events/{event.id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    photo_filename = f"{uuid.uuid4()}.jpg"
    storage_path = f"events/{event.id}/{photo_filename}"
    (storage_dir / photo_filename).write_bytes(b"fake-image-data")

    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="test.jpg",
        storage_path=storage_path,
        file_size=16,
        processing_status="complete",
        download_count=0,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/download",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200

    # Verify download_count incremented
    await db.refresh(photo)
    assert photo.download_count == 1


# ---------------------------------------------------------------------------
# Test 9: GET /photos/{id}/thumbnail → 404 when thumbnail_path is NULL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thumbnail_404_when_path_is_null(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event, thumbnail_path=None)

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/thumbnail",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 404
