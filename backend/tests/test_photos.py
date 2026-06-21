"""Tests for photo list, album-patch, and preview endpoints."""
import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.auth import create_access_token, hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="photo-owner@example.com",
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
        email="other@example.com",
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
        name="Photo Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"photo-test-{uuid.uuid4().hex[:8]}",
        status="published",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


@pytest_asyncio.fixture
async def photo(db: AsyncSession, event: Event) -> Photo:
    p = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="sample.jpg",
        storage_path=f"events/{event.id}/sample.jpg",
        file_size=2048,
        processing_status="pending",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Helper: suppress background face pipeline during upload tests
# ---------------------------------------------------------------------------

def _noop_process_photo(*args, **kwargs):
    pass


# ---------------------------------------------------------------------------
# Upload — album_id field included in response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_without_album_id(client: AsyncClient, owner_headers: dict, event: Event):
    with patch("app.routers.photos.process_photo", new=AsyncMock()):
        resp = await client.post(
            f"/api/v1/events/{event.id}/photos",
            headers=owner_headers,
            files={"file": ("photo.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["album_id"] is None
    assert body["filename"] == "photo.jpg"


@pytest.mark.asyncio
async def test_upload_with_album_id(client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession):
    # Create an album first
    from app.models.album import Album  # local import to avoid top-level dependency
    album = Album(
        id=uuid.uuid4(),
        event_id=event.id,
        name="Ceremony",
    )
    db.add(album)
    await db.commit()
    await db.refresh(album)

    with patch("app.routers.photos.process_photo", new=AsyncMock()):
        resp = await client.post(
            f"/api/v1/events/{event.id}/photos",
            headers=owner_headers,
            files={"file": ("photo.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
            data={"album_id": str(album.id)},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["album_id"] == str(album.id)


# ---------------------------------------------------------------------------
# GET "" — list photos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_photos_empty(client: AsyncClient, owner_headers: dict, event: Event):
    resp = await client.get(f"/api/v1/events/{event.id}/photos", headers=owner_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_photos_returns_photo(client: AsyncClient, owner_headers: dict, event: Event, photo: Photo):
    resp = await client.get(f"/api/v1/events/{event.id}/photos", headers=owner_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == str(photo.id)
    assert item["filename"] == "sample.jpg"
    assert item["album_id"] is None
    assert item["thumbnail_url"] is None


@pytest.mark.asyncio
async def test_list_photos_pagination(client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession):
    for i in range(5):
        db.add(Photo(
            id=uuid.uuid4(),
            event_id=event.id,
            filename=f"photo_{i}.jpg",
            storage_path=f"events/{event.id}/photo_{i}.jpg",
            file_size=1024,
            processing_status="pending",
        ))
    await db.commit()

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos?limit=3&offset=0",
        headers=owner_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["limit"] == 3
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_list_photos_requires_auth(client: AsyncClient, event: Event):
    resp = await client.get(f"/api/v1/events/{event.id}/photos")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_photos_requires_ownership(
    client: AsyncClient, other_headers: dict, event: Event
):
    resp = await client.get(f"/api/v1/events/{event.id}/photos", headers=other_headers)
    # Now returns 403 (not owner/photographer) rather than 404
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# PATCH "/{photo_id}/album"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_album_assign(
    client: AsyncClient, owner_headers: dict, event: Event, photo: Photo, db: AsyncSession
):
    from app.models.album import Album
    album = Album(id=uuid.uuid4(), event_id=event.id, name="Reception")
    db.add(album)
    await db.commit()
    await db.refresh(album)

    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{photo.id}/album",
        headers=owner_headers,
        json={"album_id": str(album.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["album_id"] == str(album.id)
    assert body["id"] == str(photo.id)


@pytest.mark.asyncio
async def test_patch_album_clear(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession
):
    from app.models.album import Album
    album = Album(id=uuid.uuid4(), event_id=event.id, name="Portraits")
    db.add(album)
    p = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        album_id=album.id,
        filename="portrait.jpg",
        storage_path=f"events/{event.id}/portrait.jpg",
        file_size=512,
        processing_status="pending",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{p.id}/album",
        headers=owner_headers,
        json={"album_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["album_id"] is None


@pytest.mark.asyncio
async def test_patch_album_photo_not_found(
    client: AsyncClient, owner_headers: dict, event: Event
):
    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{uuid.uuid4()}/album",
        headers=owner_headers,
        json={"album_id": None},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_album_requires_ownership(
    client: AsyncClient, other_headers: dict, event: Event, photo: Photo
):
    resp = await client.patch(
        f"/api/v1/events/{event.id}/photos/{photo.id}/album",
        headers=other_headers,
        json={"album_id": None},
    )
    # Now returns 403 (not owner/photographer) rather than 404
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# GET "/{photo_id}/preview"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_no_thumbnail(
    client: AsyncClient, owner_headers: dict, event: Event, photo: Photo
):
    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/preview",
        headers=owner_headers,
    )
    assert resp.status_code == 404
    assert "Thumbnail" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_preview_returns_file(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession, tmp_path: Path
):
    # Write a real thumbnail file
    thumb_file = tmp_path / "thumb.webp"
    thumb_file.write_bytes(b"FAKE_WEBP_DATA")

    # Store a relative path under tmp_path
    rel = "thumb.webp"
    p = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="main.jpg",
        storage_path=f"events/{event.id}/main.jpg",
        thumbnail_path=rel,
        file_size=1024,
        processing_status="complete",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    with patch("app.routers.photos.settings") as mock_settings:
        mock_settings.STORAGE_PATH = str(tmp_path)
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{p.id}/preview",
            headers=owner_headers,
        )
    assert resp.status_code == 200
    assert resp.content == b"FAKE_WEBP_DATA"


@pytest.mark.asyncio
async def test_preview_thumbnail_url_in_list(
    client: AsyncClient, owner_headers: dict, event: Event, db: AsyncSession
):
    """Verify list endpoint sets thumbnail_url when thumbnail_path is present."""
    p = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="main.jpg",
        storage_path=f"events/{event.id}/main.jpg",
        thumbnail_path="some/thumb.webp",
        file_size=1024,
        processing_status="complete",
    )
    db.add(p)
    await db.commit()

    resp = await client.get(f"/api/v1/events/{event.id}/photos", headers=owner_headers)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    expected = f"/api/v1/events/{event.id}/photos/{p.id}/preview"
    assert item["thumbnail_url"] == expected
