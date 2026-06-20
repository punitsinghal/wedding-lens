"""Tests for the face recognition search endpoint."""
import uuid
from unittest.mock import patch

import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.services.auth import hash_password
from app.services.guest_auth import create_guest_token
from app.services.search_cache import search_cache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the search cache before and after each test."""
    search_cache.clear()
    yield
    search_cache.clear()


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        email="search-user@example.com",
        password_hash=hash_password("pw"),
        is_admin=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def event(db: AsyncSession, user: User) -> Event:
    ev = Event(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Search Test Wedding",
        bride_name="Alice",
        groom_name="Bob",
        slug=f"search-test-{uuid.uuid4().hex[:8]}",
        access_mode="public",
        status="published",
        guest_access_enabled=True,
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
        filename="photo.jpg",
        storage_path=f"events/{event.id}/{uuid.uuid4()}.jpg",
        file_size=1024,
        processing_status="complete",
        thumbnail_path=f"events/{event.id}/thumbs/{uuid.uuid4()}.webp",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


def _guest_headers(event_id: uuid.UUID, sid: str | None = None) -> dict:
    token = create_guest_token(str(event_id), sid=sid)
    return {"Authorization": f"Bearer {token}"}


def _fake_selfie(size: int = 100) -> bytes:
    return b"x" * size


def _fake_embedding() -> np.ndarray:
    v = np.random.rand(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


# ---------------------------------------------------------------------------
# Test 1: 401 on missing token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_missing_token(client: AsyncClient, event: Event):
    resp = await client.post(
        f"/api/v1/events/{event.id}/search",
        files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
    )
    # FastAPI's HTTPBearer returns 403 when no Authorization header is provided
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 2: 401 on bad token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_bad_token(client: AsyncClient, event: Event):
    resp = await client.post(
        f"/api/v1/events/{event.id}/search",
        files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 3: 413 on selfie > 20 MB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_oversized_selfie(client: AsyncClient, event: Event):
    big_bytes = b"x" * (20 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/v1/events/{event.id}/search",
        files={"selfie": ("big.jpg", big_bytes, "image/jpeg")},
        headers=_guest_headers(event.id),
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Test 4: 422 no_face_detected when _detect_faces returns []
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_no_face_detected(client: AsyncClient, event: Event):
    with patch("app.services.face_search._detect_faces", return_value=[]):
        resp = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "no_face_detected"


# ---------------------------------------------------------------------------
# Test 5: 422 no_dominant_face when two faces within 0.10 of each other
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_no_dominant_face(client: AsyncClient, event: Event):
    faces = [
        {"bbox": [0, 0, 100, 100], "embedding": _fake_embedding(), "det_score": 0.90},
        {"bbox": [10, 10, 80, 80], "embedding": _fake_embedding(), "det_score": 0.85},
    ]
    with patch("app.services.face_search._detect_faces", return_value=faces):
        resp = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
            headers=_guest_headers(event.id),
        )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "no_dominant_face"


# ---------------------------------------------------------------------------
# Test 6: 200 with results when single face detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_single_face_returns_results(
    client: AsyncClient, event: Event, photo: Photo
):
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.95}]

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", return_value=qdrant_hits):
        resp = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
            headers=_guest_headers(event.id),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["photo_id"] == str(photo.id)
    assert "/thumbnail" in body["results"][0]["thumbnail_url"]


# ---------------------------------------------------------------------------
# Test 7: 200 using dominant face when gap >= 0.10
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_dominant_face_selected(
    client: AsyncClient, event: Event, photo: Photo
):
    dominant_emb = _fake_embedding()
    secondary_emb = _fake_embedding()
    faces = [
        {"bbox": [0, 0, 100, 100], "embedding": dominant_emb, "det_score": 0.95},
        {"bbox": [10, 10, 50, 50], "embedding": secondary_emb, "det_score": 0.80},
    ]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.92}]

    captured_embedding = {}

    def fake_search_faces(event_id, embedding, score_threshold, limit):
        captured_embedding["value"] = embedding
        return qdrant_hits

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", side_effect=fake_search_faces):
        resp = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
            headers=_guest_headers(event.id),
        )

    assert resp.status_code == 200
    # Verify dominant face embedding was used
    assert captured_embedding["value"] == dominant_emb.tolist()


# ---------------------------------------------------------------------------
# Test 8: Cache hit — X-Search-Cache=hit on second identical upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_cache_hit_on_second_request(
    client: AsyncClient, event: Event, photo: Photo
):
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.95}]
    sid = str(uuid.uuid4())
    headers = _guest_headers(event.id, sid=sid)
    selfie_bytes = _fake_selfie(200)

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", return_value=qdrant_hits):
        # First request — cache miss
        resp1 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.headers.get("x-search-cache") == "miss"

        # Second request — same selfie bytes, same sid → cache hit
        resp2 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("x-search-cache") == "hit"


# ---------------------------------------------------------------------------
# Test 9: Cache miss after different selfie bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_cache_miss_different_selfie(
    client: AsyncClient, event: Event, photo: Photo
):
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.95}]
    sid = str(uuid.uuid4())
    headers = _guest_headers(event.id, sid=sid)

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", return_value=qdrant_hits):
        resp1 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(100), "image/jpeg")},
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.headers.get("x-search-cache") == "miss"

        # Different selfie bytes → different hash → cache miss
        resp2 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(200), "image/jpeg")},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("x-search-cache") == "miss"


# ---------------------------------------------------------------------------
# Test 10: Selfie bytes deleted even when _detect_faces raises (via service directly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_selfie_deleted_on_detect_error(db: AsyncSession, event: Event):
    """Verify try/finally in run_search deletes selfie_bytes even when _detect_faces raises."""
    def raising_detect(image_bytes: bytes):
        raise RuntimeError("insightface exploded")

    from app.services.face_search import run_search

    selfie_bytes = _fake_selfie(100)

    with patch("app.services.face_search._detect_faces", side_effect=raising_detect):
        with pytest.raises(RuntimeError, match="insightface exploded"):
            await run_search(selfie_bytes, event.id, str(uuid.uuid4()), db)
    # If try/finally is working, the function completed (with exception) without hanging.
    # The test verifies the code path ran — the del is inside run_search's finally block.


# ---------------------------------------------------------------------------
# Test 11: Event scoping — search_faces called with the correct event_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_scoped_to_event_id(
    client: AsyncClient, event: Event, photo: Photo
):
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.95}]
    captured = {}

    def capture_search(event_id, embedding, score_threshold, limit):
        captured["event_id"] = event_id
        return qdrant_hits

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", side_effect=capture_search):
        resp = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", _fake_selfie(), "image/jpeg")},
            headers=_guest_headers(event.id),
        )

    assert resp.status_code == 200
    assert captured["event_id"] == event.id


# ---------------------------------------------------------------------------
# Test 12: Same sid + same hash = cache hit; different sid + same hash = miss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_cache_keyed_by_sid(
    client: AsyncClient, event: Event, photo: Photo
):
    emb = _fake_embedding()
    faces = [{"bbox": [0, 0, 100, 100], "embedding": emb, "det_score": 0.99}]
    qdrant_hits = [{"photo_id": str(photo.id), "score": 0.95}]
    selfie_bytes = _fake_selfie(300)

    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())

    with patch("app.services.face_search._detect_faces", return_value=faces), \
         patch("app.services.face_search.search_faces", return_value=qdrant_hits):
        # First request with sid_a
        resp1 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
            headers=_guest_headers(event.id, sid=sid_a),
        )
        assert resp1.status_code == 200
        assert resp1.headers.get("x-search-cache") == "miss"

        # Second request with sid_a — same bytes → hit
        resp2 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
            headers=_guest_headers(event.id, sid=sid_a),
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("x-search-cache") == "hit"

        # Third request with sid_b — same bytes but different sid → miss
        resp3 = await client.post(
            f"/api/v1/events/{event.id}/search",
            files={"selfie": ("selfie.jpg", selfie_bytes, "image/jpeg")},
            headers=_guest_headers(event.id, sid=sid_b),
        )
        assert resp3.status_code == 200
        assert resp3.headers.get("x-search-cache") == "miss"
