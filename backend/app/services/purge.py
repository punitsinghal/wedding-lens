"""
30-day purge job for soft-deleted events.

Runs daily at 02:00 via APScheduler (registered in app lifespan).
For each expired event (status='deleted', deleted_at < NOW()-30d):
  1. Deletes photo files from R2 under events/{event_id}/ (see purge_event_files)
  2. Deletes the event's Qdrant collection (app.services.qdrant.delete_collection —
     idempotent, REQ-3a/D2)
  3. Hard-deletes the event from PostgreSQL (cascades to albums, slug_redirects,
     photos, face_records, and the analytics tables)

The job is idempotent: re-running on the same event is safe.
Per-event error handling ensures one failure does not abort the entire run.

`purge_event_files` is also reused by app.routers.admin's hard-delete endpoint —
it's the single shared implementation of "delete an event's storage objects",
avoiding the pre-migration duplication where purge.py and admin.py each had
their own copy of the same shutil.rmtree call.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.event import Event
from app.models.upload_session import UploadSession
from app.routers.uploads import _object_key
from app.services import qdrant, r2

logger = logging.getLogger("weddinglens.purge")

GRACE_PERIOD_DAYS = 30


async def purge_expired_events() -> None:
    """Entry point called by APScheduler."""
    threshold = datetime.now(timezone.utc) - timedelta(days=GRACE_PERIOD_DAYS)
    logger.info(
        '{"event": "purge_job_start", "threshold": "%s"}',
        threshold.isoformat(),
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Event).where(
                Event.status == "deleted",
                Event.deleted_at < threshold,
            )
        )
        expired_events = list(result.scalars().all())

    logger.info(
        '{"event": "purge_job_found", "count": %d}',
        len(expired_events),
    )

    for event in expired_events:
        await _purge_single_event(event.id)

    logger.info('{"event": "purge_job_done"}')


async def purge_event_files(event_id: uuid.UUID) -> None:
    """Delete every R2 object under events/{event_id}/.

    Shared by the 30-day grace-period purge job and the admin hard-delete
    endpoint. This is a network call (R2 ListObjectsV2 + DeleteObjects), so
    it's dispatched via asyncio.to_thread.
    """
    count = await asyncio.to_thread(r2.delete_prefix, f"events/{event_id}/")
    logger.info(
        '{"event": "purge_files_deleted", "event_id": "%s", "count": %d}',
        event_id,
        count,
    )


async def _purge_single_event(event_id: uuid.UUID) -> None:
    try:
        # 1. Delete files from R2
        await purge_event_files(event_id)

        # 2. Delete the event's Qdrant collection (idempotent — safe if already gone)
        qdrant.delete_collection(event_id)
        logger.info(
            '{"event": "purge_qdrant_deleted", "event_id": "%s"}',
            event_id,
        )

        # 3. Hard-delete from PostgreSQL
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            if event is None:
                logger.info(
                    '{"event": "purge_already_gone", "event_id": "%s"}',
                    event_id,
                )
                return
            await db.delete(event)
            await db.commit()

        logger.info(
            '{"event": "purge_event_deleted", "event_id": "%s"}',
            event_id,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            '{"event": "purge_event_error", "event_id": "%s", "error": "%s"}',
            event_id,
            str(exc),
        )


UPLOAD_SESSION_ABANDON_HOURS = 24


async def purge_abandoned_upload_sessions() -> None:
    """
    Mark upload sessions as 'abandoned' and clean up their R2 multipart
    upload leftovers if they have been in_progress for more than
    UPLOAD_SESSION_ABANDON_HOURS.

    Called daily at 02:00 by APScheduler (registered in app lifespan).
    Idempotent: re-running on the same session is safe.
    """
    threshold = datetime.now(timezone.utc) - timedelta(hours=UPLOAD_SESSION_ABANDON_HOURS)
    logger.info(
        '{"event": "upload_purge_start", "threshold": "%s"}',
        threshold.isoformat(),
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UploadSession).where(
                UploadSession.status == "in_progress",
                UploadSession.updated_at < threshold,
            )
        )
        sessions = list(result.scalars().all())

    logger.info(
        '{"event": "upload_purge_found", "count": %d}',
        len(sessions),
    )

    for session in sessions:
        # Sessions created before this migration have no r2_upload_id — the
        # old local-disk tmp scheme they used is on a storage backend this
        # code no longer manages, so there's nothing to clean up here.
        if session.r2_upload_id is not None:
            key = _object_key(session.event_id, session.photo_id, session.filename)
            try:
                await asyncio.to_thread(
                    r2.abort_multipart_upload, key, session.r2_upload_id
                )
                logger.info(
                    '{"event": "upload_purge_multipart_aborted", "session_id": "%s"}',
                    session.id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    '{"event": "upload_purge_multipart_error", "session_id": "%s", "error": "%s"}',
                    session.id,
                    str(exc),
                )

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UploadSession).where(UploadSession.id == session.id)
            )
            s = result.scalar_one_or_none()
            if s:
                s.status = "abandoned"
                await db.commit()
                logger.info(
                    '{"event": "upload_purge_abandoned", "session_id": "%s"}',
                    session.id,
                )

    logger.info('{"event": "upload_purge_done"}')
