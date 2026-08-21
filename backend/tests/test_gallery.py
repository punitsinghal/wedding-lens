"""Gallery endpoint tests."""

import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.models.analytics import DownloadEvent, ViewEvent
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.auth import create_access_token
from app.services.guest_auth import create_guest_token
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def patch_analytics_session():
    """Redirect the fire-and-forget analytics writes to the test SQLite session.

    Mirrors the pattern in test_face_pipeline.py — background tasks open
    their own AsyncSessionLocal(), which by default is bound to the
    production engine, not the per-test SQLite session.
    """
    with patch("app.services.analytics.AsyncSessionLocal", TestSessionLocal):
        yield


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
    # Guest token is not a valid owner JWT — bearer scheme decodes it as an invalid
    # user token, so the dependency raises 401 before any ownership check.
    assert resp.status_code == 401


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


# ---------------------------------------------------------------------------
# Test 10: download writes a download_events row (D5, S6) — separate from
# Photo.download_count above.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_writes_download_event(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    import os
    from pathlib import Path

    event = await _make_event(db, regular_user)

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

    result = await db.execute(
        select(DownloadEvent).where(DownloadEvent.event_id == event.id)
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Test 11: POST /photos/{id}/view — guest view beacon (S6, D5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_view_beacon_returns_204_and_writes_view_event(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/{photo.id}/view",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 204

    result = await db.execute(select(ViewEvent).where(ViewEvent.event_id == event.id))
    rows = list(result.scalars().all())
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_view_beacon_requires_guest_auth(client: AsyncClient, db: AsyncSession, regular_user: User):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/{photo.id}/view",
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 12: GET /photos/{id}/lightbox — lazily generated, cached medium-res
# preview for the lightbox (not the /preview route in photos.py, which is
# the photographer-dashboard route serving the thumbnail — see
# docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md)
# ---------------------------------------------------------------------------


async def _make_photo_with_original(
    db: AsyncSession, event: Event, size: tuple[int, int] = (100, 50)
) -> Photo:
    """Creates a Photo row backed by a real JPEG written to STORAGE_PATH,
    so preview generation has an original file to read from."""
    import os

    from PIL import Image

    storage_dir = Path(os.environ["STORAGE_PATH"]) / f"events/{event.id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.jpg"
    storage_path = f"events/{event.id}/{filename}"

    img = Image.new("RGB", size, color=(200, 100, 50))
    img.save(storage_dir / filename, "JPEG")

    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="test.jpg",
        storage_path=storage_path,
        file_size=(storage_dir / filename).stat().st_size,
        processing_status="complete",
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


@pytest.mark.asyncio
async def test_preview_generates_and_caches_on_first_request(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    import os

    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_original(db, event, size=(100, 50))

    expected_rel_path = f"events/{event.id}/previews/{photo.id}.webp"
    expected_abs_path = Path(os.environ["STORAGE_PATH"]) / expected_rel_path
    assert not expected_abs_path.exists()

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert expected_abs_path.exists()

    preview = Image.open(expected_abs_path)
    # Small original (100x50) must never be upscaled.
    assert preview.size == (100, 50)


@pytest.mark.asyncio
async def test_preview_downscales_large_original_to_max_2000px_edge(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    import os

    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_original(db, event, size=(4000, 2000))

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200

    expected_abs_path = (
        Path(os.environ["STORAGE_PATH"]) / f"events/{event.id}/previews/{photo.id}.webp"
    )
    preview = Image.open(expected_abs_path)
    assert max(preview.size) == 2000
    assert preview.size == (2000, 1000)


@pytest.mark.asyncio
async def test_preview_second_request_serves_cached_file_without_regenerating(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    from app.services import gallery as gallery_service

    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_original(db, event)

    resp1 = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
        headers=_guest_headers(event.id),
    )
    assert resp1.status_code == 200

    with patch.object(
        gallery_service, "_generate_preview", wraps=gallery_service._generate_preview
    ) as mock_generate:
        resp2 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
        assert resp2.status_code == 200
        mock_generate.assert_not_called()


@pytest.mark.asyncio
async def test_preview_404_when_photo_not_found(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{uuid.uuid4()}/lightbox",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_preview_404_when_original_file_missing(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    # storage_path points at a file that was never written to disk.
    photo = await _make_photo(db, event)

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 13: guests must never receive a raw HEIC/HEIF file on download —
# single-photo download and ZIP download both convert to JPEG, lazily and
# cached, leaving already-JPEG/PNG originals untouched. See
# docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
# ---------------------------------------------------------------------------


def _write_heic(abs_path: Path, size: tuple[int, int] = (80, 40)) -> None:
    """Writes a real HEIC file to `abs_path` using pillow-heif."""
    from PIL import Image

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=(10, 20, 30))
    img.save(abs_path, format="HEIF")


async def _make_photo_with_heic_original(
    db: AsyncSession, event: Event, filename: str = "IMG_4521.HEIC"
) -> Photo:
    import os

    storage_dir = Path(os.environ["STORAGE_PATH"]) / f"events/{event.id}"
    storage_filename = f"{uuid.uuid4()}.heic"
    storage_path = f"events/{event.id}/{storage_filename}"
    _write_heic(storage_dir / storage_filename)

    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename=filename,
        storage_path=storage_path,
        file_size=(storage_dir / storage_filename).stat().st_size,
        processing_status="complete",
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


@pytest.mark.asyncio
async def test_download_serves_jpeg_original_unchanged(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    """An already-JPEG original must be served as-is — no re-encode, same
    bytes, same filename."""
    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_original(db, event, size=(60, 30))

    from app.services import gallery as gallery_service

    original_bytes = (
        Path(gallery_service.settings.STORAGE_PATH) / photo.storage_path
    ).read_bytes()

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/download",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    assert resp.content == original_bytes
    assert resp.headers["content-disposition"].endswith('filename="test.jpg"')


@pytest.mark.asyncio
async def test_download_converts_heic_original_to_cached_jpeg(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    import os

    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_heic_original(db, event, filename="IMG_4521.HEIC")

    expected_rel_path = f"events/{event.id}/downloads/{photo.id}.jpg"
    expected_abs_path = Path(os.environ["STORAGE_PATH"]) / expected_rel_path
    assert not expected_abs_path.exists()

    resp = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/download",
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('filename="IMG_4521.jpg"')
    assert expected_abs_path.exists()

    converted = Image.open(expected_abs_path)
    assert converted.format == "JPEG"
    assert converted.size == (80, 40)


@pytest.mark.asyncio
async def test_download_second_request_reuses_cached_conversion(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    from app.services import gallery as gallery_service

    event = await _make_event(db, regular_user)
    photo = await _make_photo_with_heic_original(db, event)

    resp1 = await client.get(
        f"/api/v1/events/{event.id}/photos/{photo.id}/download",
        headers=_guest_headers(event.id),
    )
    assert resp1.status_code == 200

    with patch.object(
        gallery_service, "_convert_to_jpeg", wraps=gallery_service._convert_to_jpeg
    ) as mock_convert:
        resp2 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
        assert resp2.status_code == 200
        mock_convert.assert_not_called()


@pytest.mark.asyncio
async def test_zip_download_converts_heic_entries_to_jpeg(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    """A ZIP containing a mix of JPEG and HEIC photos must contain only
    JPEG bytes — HEIC entries are renamed to .jpg in the archive."""
    import zipfile

    event = await _make_event(db, regular_user)
    jpeg_photo = await _make_photo_with_original(db, event, size=(40, 20))
    heic_photo = await _make_photo_with_heic_original(db, event, filename="IMG_9001.heic")

    resp = await client.post(
        f"/api/v1/events/{event.id}/photos/zip",
        headers=_guest_headers(event.id),
        json={"photo_ids": [str(jpeg_photo.id), str(heic_photo.id)]},
    )
    assert resp.status_code == 200

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "test.jpg" in names  # jpeg_photo.filename, unchanged
        assert "IMG_9001.jpg" in names  # heic_photo.filename, extension swapped
        assert not any(n.lower().endswith((".heic", ".heif")) for n in names)
