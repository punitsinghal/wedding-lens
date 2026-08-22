"""Gallery endpoint tests."""

import io
import uuid
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
from app.services import gallery as gallery_service
from app.services import r2
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
    filename: str = "test.jpg",
) -> Photo:
    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        album_id=album.id if album else None,
        filename=filename,
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


def _real_jpeg_bytes(size: tuple[int, int] = (100, 50), color=(200, 100, 50)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, "JPEG")
    return buf.getvalue()


def _real_heic_bytes(size: tuple[int, int] = (80, 40), color=(10, 20, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="HEIF")
    return buf.getvalue()


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
# Test 1b: gallery list embeds a real presigned URL for thumbnail_url
# (rather than a backend-relative path) — see
# docs/decisions/2026-08-22-presigned-url-image-delivery.md.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gallery_list_thumbnail_url_is_presigned(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event, thumbnail_path=f"events/{event.id}/thumbs/x.webp")

    signed_url = "https://r2.example.com/signed-thumb?X-Amz-Signature=abc"
    with patch("app.routers.gallery.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(
            f"/api/v1/events/{event.id}/gallery",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["photos"][0]["thumbnail_url"] == signed_url
    mock_gen.assert_called_once_with(photo.thumbnail_path)


@pytest.mark.asyncio
async def test_gallery_list_thumbnail_url_none_on_sign_failure(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    """A signing failure for one photo's thumbnail must not 500 the whole
    gallery batch — it degrades to thumbnail_url=None for that photo."""
    event = await _make_event(db, regular_user)
    await _make_photo(db, event, thumbnail_path=f"events/{event.id}/thumbs/x.webp")

    with patch(
        "app.routers.gallery.r2.generate_get_url",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.get(
            f"/api/v1/events/{event.id}/gallery",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["photos"][0]["thumbnail_url"] is None


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
# Test 8: GET /photos/{id}/download increments download_count by 1 and
# 302-redirects to the presigned R2 URL.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_increments_count(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    jpeg_header = _real_jpeg_bytes()[:16]
    signed_url = "https://r2.example.com/signed-download"

    with patch("app.services.gallery.r2.read_range", return_value=jpeg_header), \
         patch("app.routers.gallery.r2.generate_get_url", return_value=signed_url):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url

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


@pytest.mark.asyncio
async def test_thumbnail_redirects_to_presigned_url(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event, thumbnail_path=f"events/{event.id}/thumbs/x.webp")

    signed_url = "https://r2.example.com/signed-thumb"
    with patch("app.routers.gallery.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/thumbnail",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url
    mock_gen.assert_called_once_with(photo.thumbnail_path)


@pytest.mark.asyncio
async def test_thumbnail_503_when_storage_unavailable(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event, thumbnail_path=f"events/{event.id}/thumbs/x.webp")

    with patch(
        "app.routers.gallery.r2.generate_get_url",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/thumbnail",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Test 10: download writes a download_events row (D5, S6) — separate from
# Photo.download_count above.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_writes_download_event(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo(db, event)

    jpeg_header = _real_jpeg_bytes()[:16]

    with patch("app.services.gallery.r2.read_range", return_value=jpeg_header), \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/x"):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302

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


async def _make_photo_row(
    db: AsyncSession, event: Event, filename: str = "test.jpg"
) -> Photo:
    """A Photo row with no real bytes anywhere — original bytes are provided
    by mocking `r2.download_object` in each test."""
    photo = Photo(
        id=uuid.uuid4(),
        event_id=event.id,
        filename=filename,
        storage_path=f"events/{event.id}/{uuid.uuid4()}.jpg",
        file_size=1024,
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
    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event)
    original_bytes = _real_jpeg_bytes(size=(100, 50))

    captured: dict = {}

    def fake_put_object(key, body, content_type):
        captured["key"] = key
        captured["body"] = body
        captured["content_type"] = content_type

    expected_key = f"events/{event.id}/previews/{photo.id}.webp"

    with patch("app.services.gallery.r2.head_object", return_value=False), \
         patch("app.services.gallery.r2.download_object", return_value=original_bytes), \
         patch("app.services.gallery.r2.put_object", side_effect=fake_put_object), \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/preview"):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://r2.example.com/preview"
    assert captured["key"] == expected_key
    assert captured["content_type"] == "image/webp"

    preview = Image.open(io.BytesIO(captured["body"]))
    # Small original (100x50) must never be upscaled.
    assert preview.size == (100, 50)


@pytest.mark.asyncio
async def test_preview_downscales_large_original_to_max_2000px_edge(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event)
    original_bytes = _real_jpeg_bytes(size=(4000, 2000))

    captured: dict = {}

    def fake_put_object(key, body, content_type):
        captured["body"] = body

    with patch("app.services.gallery.r2.head_object", return_value=False), \
         patch("app.services.gallery.r2.download_object", return_value=original_bytes), \
         patch("app.services.gallery.r2.put_object", side_effect=fake_put_object), \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/preview"):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302

    preview = Image.open(io.BytesIO(captured["body"]))
    assert max(preview.size) == 2000
    assert preview.size == (2000, 1000)


@pytest.mark.asyncio
async def test_preview_second_request_serves_cached_file_without_regenerating(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event)
    original_bytes = _real_jpeg_bytes()

    with patch("app.services.gallery.r2.head_object", return_value=False), \
         patch("app.services.gallery.r2.download_object", return_value=original_bytes), \
         patch("app.services.gallery.r2.put_object"), \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/preview1"):
        resp1 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
    assert resp1.status_code == 302

    with patch("app.services.gallery.r2.head_object", return_value=True), \
         patch.object(
             gallery_service, "_generate_preview", wraps=gallery_service._generate_preview
         ) as mock_generate, \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/preview2"):
        resp2 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
        assert resp2.status_code == 302
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
    photo = await _make_photo_row(db, event)

    with patch("app.services.gallery.r2.head_object", return_value=False), \
         patch(
             "app.services.gallery.r2.download_object",
             side_effect=r2.StorageUnavailableError("missing"),
         ):
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/lightbox",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 13: guests must never receive a raw HEIC/HEIF file on download —
# single-photo download converts to JPEG, lazily and cached, leaving
# already-JPEG/PNG originals untouched. See
# docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_serves_jpeg_original_unchanged(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    """An already-JPEG original must be served as-is — no re-encode, no
    cached conversion object written, same storage key used for the
    presigned URL, same filename."""
    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event, filename="test.jpg")
    jpeg_header = _real_jpeg_bytes()[:16]
    signed_url = "https://r2.example.com/signed-download"

    with patch("app.services.gallery.r2.read_range", return_value=jpeg_header), \
         patch("app.services.gallery.r2.put_object") as mock_put, \
         patch("app.routers.gallery.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url
    mock_put.assert_not_called()
    mock_gen.assert_called_once_with(
        photo.storage_path,
        response_content_disposition='attachment; filename="test.jpg"',
    )


@pytest.mark.asyncio
async def test_download_converts_heic_original_to_cached_jpeg(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    from PIL import Image

    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event, filename="IMG_4521.HEIC")
    heic_bytes = _real_heic_bytes(size=(80, 40))
    heic_header = heic_bytes[:16]

    captured: dict = {}

    def fake_put_object(key, body, content_type):
        captured["key"] = key
        captured["body"] = body
        captured["content_type"] = content_type

    expected_key = f"events/{event.id}/downloads/{photo.id}.jpg"
    signed_url = "https://r2.example.com/signed-jpeg"

    with patch("app.services.gallery.r2.read_range", return_value=heic_header), \
         patch("app.services.gallery.r2.head_object", return_value=False), \
         patch("app.services.gallery.r2.download_object", return_value=heic_bytes), \
         patch("app.services.gallery.r2.put_object", side_effect=fake_put_object), \
         patch("app.routers.gallery.r2.generate_get_url", return_value=signed_url) as mock_gen:
        resp = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 302
    assert resp.headers["location"] == signed_url
    assert captured["key"] == expected_key
    assert captured["content_type"] == "image/jpeg"

    converted = Image.open(io.BytesIO(captured["body"]))
    assert converted.format == "JPEG"
    assert converted.size == (80, 40)

    mock_gen.assert_called_once_with(
        expected_key,
        response_content_disposition='attachment; filename="IMG_4521.jpg"',
    )


@pytest.mark.asyncio
async def test_download_second_request_reuses_cached_conversion(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    event = await _make_event(db, regular_user)
    photo = await _make_photo_row(db, event, filename="IMG_4521.HEIC")
    heic_bytes = _real_heic_bytes()
    heic_header = heic_bytes[:16]

    with patch("app.services.gallery.r2.read_range", return_value=heic_header), \
         patch("app.services.gallery.r2.head_object", return_value=False), \
         patch("app.services.gallery.r2.download_object", return_value=heic_bytes), \
         patch("app.services.gallery.r2.put_object"), \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/1"):
        resp1 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
    assert resp1.status_code == 302

    with patch("app.services.gallery.r2.read_range", return_value=heic_header), \
         patch("app.services.gallery.r2.head_object", return_value=True), \
         patch.object(
             gallery_service, "_convert_to_jpeg", wraps=gallery_service._convert_to_jpeg
         ) as mock_convert, \
         patch("app.routers.gallery.r2.generate_get_url", return_value="https://r2.example.com/2"):
        resp2 = await client.get(
            f"/api/v1/events/{event.id}/photos/{photo.id}/download",
            headers=_guest_headers(event.id),
        )
        assert resp2.status_code == 302
        mock_convert.assert_not_called()


# ---------------------------------------------------------------------------
# Test 14: ZIP download still converts HEIC entries to JPEG. `zip_streaming.py`
# now fetches originals from R2 (like the rest of this module), so this test
# mocks `app.services.zip_streaming.r2.*` the same way the single-download
# tests above mock `app.services.gallery.r2.*`.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zip_download_converts_heic_entries_to_jpeg(
    client: AsyncClient, db: AsyncSession, regular_user: User
):
    """A ZIP containing a mix of JPEG and HEIC photos must contain only
    JPEG bytes — HEIC entries are renamed to .jpg in the archive."""
    import zipfile

    event = await _make_event(db, regular_user)
    jpeg_photo = await _make_photo_row(db, event, filename="test.jpg")
    heic_photo = await _make_photo_row(db, event, filename="IMG_9001.heic")

    jpeg_bytes = _real_jpeg_bytes(size=(40, 20))
    heic_bytes = _real_heic_bytes(size=(80, 40))
    originals = {
        jpeg_photo.storage_path: jpeg_bytes,
        heic_photo.storage_path: heic_bytes,
    }

    with patch(
        "app.services.zip_streaming.r2.read_range",
        side_effect=lambda key, start, end: originals[key][:16],
    ), patch(
        "app.services.zip_streaming.r2.download_object",
        side_effect=lambda key: originals[key],
    ), patch(
        "app.services.zip_streaming.r2.head_object", return_value=False
    ), patch("app.services.zip_streaming.r2.put_object"):
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
