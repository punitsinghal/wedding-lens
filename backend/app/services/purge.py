"""
30-day purge job for soft-deleted events.

Runs daily at 02:00 via APScheduler (registered in app lifespan).
For each expired event (status='deleted', deleted_at < NOW()-30d):
  1. Deletes photo files from STORAGE_PATH/events/{event_id}/
  2. Stubs out Qdrant deletion (logs it — Qdrant not set up yet)
  3. Hard-deletes the event from PostgreSQL (cascades to albums, slug_redirects)

The job is idempotent: re-running on the same event is safe.
Per-event error handling ensures one failure does not abort the entire run.
"""

import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.event import Event

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


async def _purge_single_event(event_id: uuid.UUID) -> None:
    try:
        # 1. Delete files from local storage
        event_path = Path(settings.STORAGE_PATH) / "events" / str(event_id)
        if event_path.exists():
            shutil.rmtree(event_path)
            logger.info(
                '{"event": "purge_files_deleted", "event_id": "%s", "path": "%s"}',
                event_id,
                str(event_path),
            )
        else:
            logger.info(
                '{"event": "purge_files_no_path", "event_id": "%s"}',
                event_id,
            )

        # 2. Stub: Qdrant vector deletion (not yet set up)
        _stub_qdrant_delete(event_id)

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


def _stub_qdrant_delete(event_id: uuid.UUID) -> None:
    """
    Qdrant is not set up yet. This stub logs the intended operation so that
    the purge job can be wired to real Qdrant calls in a future epic without
    changing the job structure.
    """
    logger.info(
        '{"event": "purge_qdrant_stub", "event_id": "%s", "action": "delete_by_filter", "filter": {"event_id": "%s"}}',
        event_id,
        event_id,
    )
