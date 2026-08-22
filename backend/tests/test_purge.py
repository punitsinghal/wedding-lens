"""Tests for the 30-day event purge job and abandoned upload-session cleanup
(app.services.purge).

Covers:
  - purge_event_files: shared R2 storage-cleanup used by both the purge job
    and the admin hard-delete endpoint (see test_admin.py for the latter).
  - _purge_single_event: storage + Qdrant + DB cascade, idempotent re-run,
    per-event error isolation.
  - purge_abandoned_upload_sessions: R2-multipart-abort vs no-op branch,
    DB status update regardless of storage-cleanup outcome.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services import purge
from app.services.r2 import StorageUnavailableError

# Redirect purge's AsyncSessionLocal to the test SQLite session — same
# pattern as tests/test_admin_alerts.py / tests/test_face_pipeline.py.
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def patch_async_session_local():
    with patch("app.services.purge.AsyncSessionLocal", TestSessionLocal):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_deleted_event(db: AsyncSession, owner: User, slug: str, days_ago: int) -> Event:
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="Wedding",
        bride_name="A",
        groom_name="B",
        slug=slug,
        status="deleted",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def _make_upload_session(
    db: AsyncSession,
    event: Event,
    owner: User,
    *,
    r2_upload_id: str | None,
    hours_ago: int,
) -> UploadSession:
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event.id,
        uploader_id=owner.id,
        filename="photo.jpg",
        file_size_bytes=1024,
        content_hash="hash-" + str(uuid.uuid4()),
        chunk_size_bytes=8 * 1024 * 1024,
        total_chunks=1,
        received_chunks=[],
        status="in_progress",
        photo_id=uuid.uuid4(),
        r2_upload_id=r2_upload_id,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _fetch_session_status(session_id: uuid.UUID) -> str:
    """Re-fetch an UploadSession's status via a brand-new session/connection.

    `purge_abandoned_upload_sessions` commits via its own, separately-opened
    `AsyncSessionLocal` session (patched to the test engine). Empirically,
    this fixture file's long-lived `db` fixture session does not observe
    that other session's commit even after `db.expire_all()` or `db.commit()`
    on the fixture session — only a freshly opened session reliably sees it.
    Route verification queries through this helper instead of the `db`
    fixture for any assertion that needs to see a write made by code under
    test that uses `AsyncSessionLocal` directly.
    """
    async with TestSessionLocal() as fresh:
        result = await fresh.execute(select(UploadSession).where(UploadSession.id == session_id))
        return result.scalar_one().status


# ---------------------------------------------------------------------------
# purge_event_files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_event_files_calls_delete_prefix_with_event_scoped_key():
    event_id = uuid.uuid4()
    with patch("app.services.purge.r2.delete_prefix", return_value=3) as mock_delete:
        await purge.purge_event_files(event_id)
    mock_delete.assert_called_once_with(f"events/{event_id}/")


@pytest.mark.asyncio
async def test_purge_event_files_idempotent_when_zero_objects():
    """Matches pre-migration local-disk behavior: an already-empty/missing
    prefix is a no-op, not an error."""
    event_id = uuid.uuid4()
    with patch("app.services.purge.r2.delete_prefix", return_value=0) as mock_delete:
        await purge.purge_event_files(event_id)
    mock_delete.assert_called_once()


# ---------------------------------------------------------------------------
# _purge_single_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_single_event_deletes_storage_qdrant_and_db(
    db: AsyncSession, regular_user: User
):
    event = await _make_deleted_event(db, regular_user, "purge-1", days_ago=31)

    with patch("app.services.purge.r2.delete_prefix", return_value=5) as mock_delete_prefix, \
         patch("app.services.purge.qdrant.delete_collection") as mock_qdrant_delete:
        await purge._purge_single_event(event.id)

    mock_delete_prefix.assert_called_once_with(f"events/{event.id}/")
    mock_qdrant_delete.assert_called_once_with(event.id)

    result = await db.execute(select(Event).where(Event.id == event.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_purge_single_event_idempotent_on_rerun(
    db: AsyncSession, regular_user: User
):
    """Re-running on an already-purged event is safe (event row already
    gone) — no exception, no duplicate work."""
    event = await _make_deleted_event(db, regular_user, "purge-2", days_ago=31)

    with patch("app.services.purge.r2.delete_prefix", return_value=1), \
         patch("app.services.purge.qdrant.delete_collection"):
        await purge._purge_single_event(event.id)

    with patch("app.services.purge.r2.delete_prefix", return_value=0) as mock_delete_prefix, \
         patch("app.services.purge.qdrant.delete_collection") as mock_qdrant_delete:
        # Should not raise even though the event row no longer exists.
        await purge._purge_single_event(event.id)

    mock_delete_prefix.assert_called_once()
    mock_qdrant_delete.assert_called_once()


@pytest.mark.asyncio
async def test_purge_single_event_error_does_not_raise(
    db: AsyncSession, regular_user: User
):
    """A storage failure for one event must be caught and logged, not raised —
    callers (purge_expired_events) rely on this to keep processing the rest
    of the batch."""
    event = await _make_deleted_event(db, regular_user, "purge-3", days_ago=31)

    with patch(
        "app.services.purge.r2.delete_prefix",
        side_effect=StorageUnavailableError("boom"),
    ):
        # Must not raise.
        await purge._purge_single_event(event.id)

    # Event row must still exist — DB step never ran because storage failed.
    result = await db.execute(select(Event).where(Event.id == event.id))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_purge_expired_events_continues_after_one_failure(
    db: AsyncSession, regular_user: User
):
    """Per-event error handling: one event's storage failure does not abort
    the rest of the batch."""
    bad_event = await _make_deleted_event(db, regular_user, "purge-bad", days_ago=31)
    good_event = await _make_deleted_event(db, regular_user, "purge-good", days_ago=31)

    def fake_delete_prefix(prefix: str) -> int:
        if str(bad_event.id) in prefix:
            raise StorageUnavailableError("boom")
        return 0

    with patch("app.services.purge.r2.delete_prefix", side_effect=fake_delete_prefix), \
         patch("app.services.purge.qdrant.delete_collection"):
        await purge.purge_expired_events()

    result = await db.execute(select(Event).where(Event.id == bad_event.id))
    assert result.scalar_one_or_none() is not None, "failed event should survive for retry"

    result = await db.execute(select(Event).where(Event.id == good_event.id))
    assert result.scalar_one_or_none() is None, "good event should still be purged"


@pytest.mark.asyncio
async def test_purge_expired_events_ignores_non_expired(
    db: AsyncSession, regular_user: User
):
    recent_event = await _make_deleted_event(db, regular_user, "purge-recent", days_ago=1)

    with patch("app.services.purge.r2.delete_prefix") as mock_delete_prefix, \
         patch("app.services.purge.qdrant.delete_collection"):
        await purge.purge_expired_events()

    mock_delete_prefix.assert_not_called()
    result = await db.execute(select(Event).where(Event.id == recent_event.id))
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# purge_abandoned_upload_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abandoned_session_with_r2_upload_id_aborts_multipart(
    db: AsyncSession, regular_user: User
):
    event = await _make_deleted_event(db, regular_user, "abandon-1", days_ago=0)
    session = await _make_upload_session(
        db, event, regular_user, r2_upload_id="upload-abc", hours_ago=25
    )

    with patch("app.services.purge.r2.abort_multipart_upload") as mock_abort:
        await purge.purge_abandoned_upload_sessions()

    expected_key = f"events/{event.id}/{session.photo_id}.jpg"
    mock_abort.assert_called_once_with(expected_key, "upload-abc")

    assert await _fetch_session_status(session.id) == "abandoned"


@pytest.mark.asyncio
async def test_abandoned_session_without_r2_upload_id_skips_storage_cleanup(
    db: AsyncSession, regular_user: User
):
    """Pre-migration sessions have no r2_upload_id — nothing to abort, and no
    local filesystem operation should be attempted."""
    event = await _make_deleted_event(db, regular_user, "abandon-2", days_ago=0)
    session = await _make_upload_session(
        db, event, regular_user, r2_upload_id=None, hours_ago=25
    )

    with patch("app.services.purge.r2.abort_multipart_upload") as mock_abort:
        await purge.purge_abandoned_upload_sessions()

    mock_abort.assert_not_called()
    assert await _fetch_session_status(session.id) == "abandoned"


@pytest.mark.asyncio
async def test_abandoned_session_marks_abandoned_even_if_abort_fails(
    db: AsyncSession, regular_user: User
):
    """Storage-cleanup failure must not block the DB status transition —
    matches the pre-migration behavior for local tmp-dir cleanup failures."""
    event = await _make_deleted_event(db, regular_user, "abandon-3", days_ago=0)
    session = await _make_upload_session(
        db, event, regular_user, r2_upload_id="upload-fails", hours_ago=25
    )

    with patch(
        "app.services.purge.r2.abort_multipart_upload",
        side_effect=StorageUnavailableError("boom"),
    ):
        # Must not raise.
        await purge.purge_abandoned_upload_sessions()

    assert await _fetch_session_status(session.id) == "abandoned"


@pytest.mark.asyncio
async def test_purge_abandoned_upload_sessions_ignores_recent(
    db: AsyncSession, regular_user: User
):
    event = await _make_deleted_event(db, regular_user, "abandon-4", days_ago=0)
    session = await _make_upload_session(
        db, event, regular_user, r2_upload_id="upload-recent", hours_ago=1
    )

    with patch("app.services.purge.r2.abort_multipart_upload") as mock_abort:
        await purge.purge_abandoned_upload_sessions()

    mock_abort.assert_not_called()
    assert await _fetch_session_status(session.id) == "in_progress"
