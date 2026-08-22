"""Admin endpoint tests."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.services import qdrant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def make_event(client: AsyncClient, headers: dict, slug: str) -> str:
    payload = {
        "name": "Wedding",
        "bride_name": "Admin",
        "groom_name": "Test",
        "access_mode": "public",
        "slug": slug,
    }
    resp = await client.post("/api/v1/events", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_photo(
    db: AsyncSession,
    event_id: uuid.UUID,
    file_size: int = 1024,
    processing_status: str = "complete",
    last_processed_at: datetime | None = None,
) -> Photo:
    photo = Photo(
        id=uuid.uuid4(),
        event_id=event_id,
        filename="photo.jpg",
        storage_path=f"events/{event_id}/{uuid.uuid4()}.jpg",
        file_size=file_size,
        processing_status=processing_status,
        last_processed_at=last_processed_at,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


# ---------------------------------------------------------------------------
# List events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_events(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    await make_event(client, auth_headers, "event-admin-1")
    await make_event(client, auth_headers, "event-admin-2")
    resp = await client.get("/api/v1/admin/events", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert "items" in body
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_admin_list_events_pagination(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    for i in range(5):
        await make_event(client, auth_headers, f"pag-event-{i}")
    resp = await client.get(
        "/api/v1/admin/events?page=1&page_size=2", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["page_size"] == 2


@pytest.mark.asyncio
async def test_admin_list_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/admin/events", headers=auth_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Suspend / unsuspend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_suspend_event(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "suspend-me")
    resp = await client.post(
        f"/api/v1/admin/events/{event_id}/suspend", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "suspended"


@pytest.mark.asyncio
async def test_admin_unsuspend_event(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "unsuspend-me")
    await client.post(f"/api/v1/admin/events/{event_id}/suspend", headers=admin_headers)
    resp = await client.post(
        f"/api/v1/admin/events/{event_id}/unsuspend", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_suspend_nonexistent_event(client: AsyncClient, admin_headers: dict):
    resp = await client.post(
        f"/api/v1/admin/events/{uuid.uuid4()}/suspend", headers=admin_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Hard delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_hard_delete(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    with patch("app.services.qdrant.delete_collection") as mock_delete, \
         patch("app.services.purge.r2.delete_prefix", return_value=0) as mock_delete_prefix:
        event_id = await make_event(client, auth_headers, "hard-delete-me")
        resp = await client.delete(
            f"/api/v1/admin/events/{event_id}", headers=admin_headers
        )
    assert resp.status_code == 204
    # Confirm gone
    resp = await client.get(f"/api/v1/events/{event_id}", headers=auth_headers)
    assert resp.status_code == 404
    # REQ-3a/D2 — the stub is gone; the real qdrant.delete_collection is called.
    mock_delete.assert_called_once_with(uuid.UUID(event_id))
    # Storage cleanup goes through the shared purge_event_files -> R2 delete_prefix,
    # not a local shutil.rmtree.
    mock_delete_prefix.assert_called_once_with(f"events/{event_id}/")


@pytest.mark.asyncio
async def test_admin_hard_delete_calls_real_qdrant_delete_not_stub(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """AC-3d — _stub_qdrant_delete must no longer be called anywhere in the
    delete path. Confirms the function doesn't even exist anymore."""
    import app.services.purge as purge_module

    assert not hasattr(purge_module, "_stub_qdrant_delete")

    with patch("app.services.qdrant.delete_collection") as mock_delete, \
         patch("app.services.purge.r2.delete_prefix", return_value=0):
        event_id = await make_event(client, auth_headers, "hard-delete-real")
        resp = await client.delete(
            f"/api/v1/admin/events/{event_id}", headers=admin_headers
        )
    assert resp.status_code == 204
    mock_delete.assert_called_once()


def test_qdrant_delete_collection_idempotent_on_404():
    """D2 — delete_collection must treat a 404 (collection already gone /
    never created) as success, matching search_faces's existing pattern."""
    fake_client = type(
        "FakeClient",
        (),
        {
            "delete_collection": lambda self, name: (_ for _ in ()).throw(
                UnexpectedResponse(
                    status_code=404,
                    reason_phrase="Not Found",
                    content=b"not found",
                    headers=None,
                )
            )
        },
    )()

    with patch("app.services.qdrant.get_qdrant_client", return_value=fake_client):
        # Must not raise.
        qdrant.delete_collection(uuid.uuid4())


def test_qdrant_delete_collection_reraises_non_404():
    """Non-404 errors must still propagate — only 404 is treated as success."""
    fake_client = type(
        "FakeClient",
        (),
        {
            "delete_collection": lambda self, name: (_ for _ in ()).throw(
                UnexpectedResponse(
                    status_code=500,
                    reason_phrase="Internal Server Error",
                    content=b"boom",
                    headers=None,
                )
            )
        },
    )()

    with patch("app.services.qdrant.get_qdrant_client", return_value=fake_client):
        with pytest.raises(UnexpectedResponse):
            qdrant.delete_collection(uuid.uuid4())


@pytest.mark.asyncio
async def test_admin_hard_delete_nonexistent(client: AsyncClient, admin_headers: dict):
    resp = await client.delete(
        f"/api/v1/admin/events/{uuid.uuid4()}", headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_delete_requires_admin(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.delete(
        f"/api/v1/admin/events/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List — amended with photo_count / storage_used_bytes / last_activity_at (D1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_events_includes_stats(
    client: AsyncClient, db: AsyncSession, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "stats-event")
    await _make_photo(db, uuid.UUID(event_id), file_size=100)
    await _make_photo(db, uuid.UUID(event_id), file_size=250)

    resp = await client.get("/api/v1/admin/events", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    row = next(i for i in items if i["id"] == event_id)
    assert row["photo_count"] == 2
    assert row["storage_used_bytes"] == 350
    assert row["last_activity_at"] is not None


@pytest.mark.asyncio
async def test_admin_list_events_no_photos_falls_back_to_updated_at(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "no-photos-event")
    resp = await client.get("/api/v1/admin/events", headers=admin_headers)
    items = resp.json()["items"]
    row = next(i for i in items if i["id"] == event_id)
    assert row["photo_count"] == 0
    assert row["storage_used_bytes"] == 0
    # Falls back to Event.updated_at when no photos exist yet (D1).
    assert row["last_activity_at"] == row["updated_at"]


@pytest.mark.asyncio
async def test_admin_list_events_filter_by_status(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "filter-suspend-me")
    await client.post(f"/api/v1/admin/events/{event_id}/suspend", headers=admin_headers)

    resp = await client.get("/api/v1/admin/events?status=suspended", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["status"] == "suspended" for i in items)
    assert any(i["id"] == event_id for i in items)

    resp2 = await client.get("/api/v1/admin/events?status=draft", headers=admin_headers)
    assert all(i["id"] != event_id for i in resp2.json()["items"])


@pytest.mark.asyncio
async def test_admin_list_events_sort_by_photo_count(
    client: AsyncClient, db: AsyncSession, auth_headers: dict, admin_headers: dict
):
    small_id = await make_event(client, auth_headers, "sort-small")
    big_id = await make_event(client, auth_headers, "sort-big")
    await _make_photo(db, uuid.UUID(small_id))
    for _ in range(3):
        await _make_photo(db, uuid.UUID(big_id))

    resp = await client.get(
        "/api/v1/admin/events?sort=photo_count&page_size=100", headers=admin_headers
    )
    items = resp.json()["items"]
    ids_in_order = [i["id"] for i in items]
    assert ids_in_order.index(big_id) < ids_in_order.index(small_id)


@pytest.mark.asyncio
async def test_admin_list_events_sort_by_last_activity(
    client: AsyncClient, db: AsyncSession, auth_headers: dict, admin_headers: dict
):
    old_id = await make_event(client, auth_headers, "sort-old-activity")
    new_id = await make_event(client, auth_headers, "sort-new-activity")
    now = datetime.now(timezone.utc)
    await _make_photo(db, uuid.UUID(old_id))
    photo = await _make_photo(db, uuid.UUID(new_id))
    # Force distinguishable created_at ordering (last_activity_at = MAX(created_at)).
    old_photo_result = await db.execute(
        Photo.__table__.select().where(Photo.event_id == uuid.UUID(old_id))
    )
    old_photo_row = old_photo_result.first()
    await db.execute(
        Photo.__table__.update()
        .where(Photo.id == old_photo_row.id)
        .values(created_at=now - timedelta(days=10))
    )
    await db.execute(
        Photo.__table__.update()
        .where(Photo.id == photo.id)
        .values(created_at=now)
    )
    await db.commit()

    resp = await client.get(
        "/api/v1/admin/events?sort=last_activity&page_size=100", headers=admin_headers
    )
    items = resp.json()["items"]
    ids_in_order = [i["id"] for i in items]
    assert ids_in_order.index(new_id) < ids_in_order.index(old_id)


# ---------------------------------------------------------------------------
# Detail — context fields + processing monitor (D1, D3, REQ-2/4a/4b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_event_detail_context_and_monitor(
    client: AsyncClient, db: AsyncSession, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "detail-event")
    eid = uuid.UUID(event_id)
    await _make_photo(db, eid, file_size=100, processing_status="pending")
    await _make_photo(db, eid, file_size=100, processing_status="processing")
    await _make_photo(db, eid, file_size=100, processing_status="complete")
    await _make_photo(db, eid, file_size=100, processing_status="complete")
    await _make_photo(db, eid, file_size=100, processing_status="failed")
    await _make_photo(db, eid, file_size=100, processing_status="error")

    resp = await client.get(f"/api/v1/admin/events/{event_id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["photo_count"] == 6
    assert body["storage_used_bytes"] == 600
    monitor = body["processing_monitor"]
    assert monitor == {
        "pending": 1,
        "processing": 1,
        "complete": 2,
        "failed": 1,
        "error": 1,
    }


@pytest.mark.asyncio
async def test_admin_event_detail_404(client: AsyncClient, admin_headers: dict):
    resp = await client.get(f"/api/v1/admin/events/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_event_detail_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/v1/admin/events/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Platform health dashboard (D6, REQ-7a/7b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_health_dashboard(
    client: AsyncClient, db: AsyncSession, auth_headers: dict, admin_headers: dict
):
    event_id = await make_event(client, auth_headers, "health-event")
    eid = uuid.UUID(event_id)
    now = datetime.now(timezone.utc)

    # In the trailing 24h window: 1 failed, 1 error, 2 complete → rate = 2/4 = 0.5
    await _make_photo(db, eid, file_size=500, processing_status="failed", last_processed_at=now)
    await _make_photo(db, eid, file_size=500, processing_status="error", last_processed_at=now)
    await _make_photo(db, eid, file_size=500, processing_status="complete", last_processed_at=now)
    await _make_photo(db, eid, file_size=500, processing_status="complete", last_processed_at=now)
    # Outside the window — must not count toward the rate.
    await _make_photo(
        db, eid, file_size=500, processing_status="error",
        last_processed_at=now - timedelta(hours=25),
    )

    resp = await client.get("/api/v1/admin/health", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_events"] >= 1
    assert body["total_photos"] >= 5
    assert body["total_storage_bytes"] >= 2500
    assert body["error_rate_24h"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_admin_health_requires_admin(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/admin/health", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_health_zero_denominator_returns_zero_rate(
    client: AsyncClient, admin_headers: dict
):
    """No photos processed in the last 24h anywhere → error_rate_24h is 0.0,
    not a ZeroDivisionError."""
    resp = await client.get("/api/v1/admin/health", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["error_rate_24h"] == 0.0
