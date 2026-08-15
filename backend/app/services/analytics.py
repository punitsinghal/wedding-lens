"""Event-scoped analytics — write path (fire-and-forget) and read path (D5).

Write path (record_*_event): these are called from FastAPI BackgroundTasks
after the guest-facing response has already been prepared (NFR-3 — a write
failure must never surface to the guest). Each function opens its OWN
AsyncSessionLocal() session rather than reusing the request's `db` session,
mirroring the existing BackgroundTasks pattern in app.services.face_pipeline
(request-scoped sessions are closed by the time a background task runs).

Read path (get_event_analytics): simple COUNT(*) per table, scoped by
event_id, called synchronously within the owner-analytics request.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.analytics import DownloadEvent, SearchEvent, ViewEvent

logger = logging.getLogger("weddinglens.analytics")


async def _record(model: type, event_id: uuid.UUID, label: str) -> None:
    """Insert one row. Swallows all errors — analytics writes must never
    raise into the caller (NFR-3)."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(model(id=uuid.uuid4(), event_id=event_id))
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — fire-and-forget by design
        logger.error(
            '{"event": "analytics_write_error", "type": "%s", "event_id": "%s", "error": "%s"}',
            label,
            str(event_id),
            str(exc),
        )


async def record_view_event(event_id: uuid.UUID) -> None:
    await _record(ViewEvent, event_id, "view")


async def record_download_event(event_id: uuid.UUID) -> None:
    await _record(DownloadEvent, event_id, "download")


async def record_search_event(event_id: uuid.UUID) -> None:
    await _record(SearchEvent, event_id, "search")


async def get_event_analytics(db: AsyncSession, event_id: uuid.UUID) -> dict[str, int]:
    """Total views/downloads/searches for an event (REQ-6a) — simple COUNT(*)."""
    view_count = (
        await db.execute(
            select(func.count()).select_from(ViewEvent).where(ViewEvent.event_id == event_id)
        )
    ).scalar_one()
    download_count = (
        await db.execute(
            select(func.count())
            .select_from(DownloadEvent)
            .where(DownloadEvent.event_id == event_id)
        )
    ).scalar_one()
    search_count = (
        await db.execute(
            select(func.count()).select_from(SearchEvent).where(SearchEvent.event_id == event_id)
        )
    ).scalar_one()
    return {
        "total_views": view_count,
        "total_downloads": download_count,
        "total_searches": search_count,
    }
