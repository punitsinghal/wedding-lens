"""Admin platform aggregation queries (design D1, D3, D6).

All context fields (photo_count, storage_used_bytes, last_activity_at) and
the processing monitor are computed at query time via aggregation — not
denormalized onto Event/Photo (D1). No caching (D6); NFR-1 (<=500 events)
means these batch queries comfortably meet the 3-second budget.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.photo import Photo

# D3 — all 5 real processing_status values (see face_pipeline.py:243).
PROCESSING_STATUSES = ("pending", "processing", "complete", "failed", "error")

_VALID_SORTS = ("last_activity", "photo_count")


async def list_events_with_stats(
    db: AsyncSession,
    page: int,
    page_size: int,
    status_filter: str | None = None,
    sort: str | None = None,
) -> tuple[list[tuple[Event, int, int, datetime]], int]:
    """Paginated event list with photo_count/storage_used_bytes/last_activity_at.

    Single aggregated query (LEFT JOIN + GROUP BY event_id) — no N+1 (D1).
    Returns a list of (event, photo_count, storage_used_bytes, last_activity_at)
    tuples plus the total row count (post status-filter, pre-pagination).
    """
    photo_agg = (
        select(
            Photo.event_id.label("event_id"),
            func.count(Photo.id).label("photo_count"),
            func.coalesce(func.sum(Photo.file_size), 0).label("storage_used_bytes"),
            func.max(Photo.created_at).label("last_photo_at"),
        )
        .group_by(Photo.event_id)
        .subquery()
    )

    photo_count_col = func.coalesce(photo_agg.c.photo_count, 0)
    storage_col = func.coalesce(photo_agg.c.storage_used_bytes, 0)
    # Falls back to Event.updated_at when the event has no photos yet (D1).
    last_activity_col = func.coalesce(photo_agg.c.last_photo_at, Event.updated_at)

    base_stmt = select(Event.id).outerjoin(
        photo_agg, photo_agg.c.event_id == Event.id
    )
    if status_filter is not None:
        base_stmt = base_stmt.where(Event.status == status_filter)
    total = (
        await db.execute(select(func.count()).select_from(base_stmt.subquery()))
    ).scalar_one()

    stmt = select(Event, photo_count_col, storage_col, last_activity_col).outerjoin(
        photo_agg, photo_agg.c.event_id == Event.id
    )
    if status_filter is not None:
        stmt = stmt.where(Event.status == status_filter)

    if sort == "photo_count":
        stmt = stmt.order_by(photo_count_col.desc())
    elif sort == "last_activity":
        stmt = stmt.order_by(last_activity_col.desc())
    else:
        stmt = stmt.order_by(Event.created_at.desc())

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    rows = [(row[0], row[1], row[2], row[3]) for row in result.all()]
    return rows, total


async def get_event_with_stats(
    db: AsyncSession, event_id: uuid.UUID
) -> tuple[Event, int, int, datetime] | None:
    """Single event's photo_count/storage_used_bytes/last_activity_at (D1).

    Returns None if the event does not exist (caller should 404).
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        return None

    agg_result = await db.execute(
        select(
            func.count(Photo.id),
            func.coalesce(func.sum(Photo.file_size), 0),
            func.max(Photo.created_at),
        ).where(Photo.event_id == event_id)
    )
    photo_count, storage_used_bytes, last_photo_at = agg_result.one()
    last_activity_at = last_photo_at or event.updated_at
    return event, photo_count, storage_used_bytes, last_activity_at


async def get_processing_monitor(
    db: AsyncSession, event_id: uuid.UUID
) -> dict[str, int]:
    """Per-event processing_status breakdown (D3, REQ-4a/4b).

    Uses the existing ix_photos_event_status index — one GROUP BY query.
    Always returns all 5 keys, defaulting missing states to 0.
    """
    result = await db.execute(
        select(Photo.processing_status, func.count(Photo.id))
        .where(Photo.event_id == event_id)
        .group_by(Photo.processing_status)
    )
    counts = {s: 0 for s in PROCESSING_STATUSES}
    for status_val, cnt in result.all():
        if status_val in counts:
            counts[status_val] = cnt
    return counts


async def get_platform_health(db: AsyncSession) -> dict:
    """Platform-wide health metrics (D6, REQ-7a/7b) — batch queries, no caching."""
    total_events = (
        await db.execute(select(func.count()).select_from(Event))
    ).scalar_one()

    photo_totals = (
        await db.execute(
            select(func.count(Photo.id), func.coalesce(func.sum(Photo.file_size), 0))
        )
    ).one()
    total_photos, total_storage_bytes = photo_totals

    window_start = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(Photo.processing_status, func.count(Photo.id))
        .where(Photo.last_processed_at > window_start)
        .group_by(Photo.processing_status)
    )
    counts = {s: 0 for s in PROCESSING_STATUSES}
    for status_val, cnt in result.all():
        if status_val in counts:
            counts[status_val] = cnt

    failed = counts["failed"]
    error = counts["error"]
    complete = counts["complete"]
    denom = failed + error + complete
    error_rate_24h = (failed + error) / denom if denom > 0 else 0.0

    return {
        "total_events": total_events,
        "total_photos": total_photos,
        "total_storage_bytes": total_storage_bytes,
        "error_rate_24h": error_rate_24h,
    }
