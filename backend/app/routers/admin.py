"""Admin endpoints (is_admin JWT required)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin
from app.models.privacy import RemovalRequest
from app.models.user import User
from app.schemas.admin import (
    AdminEventDetailOut,
    AdminEventListItem,
    PaginatedAdminEvents,
    PlatformHealthOut,
    ProcessingMonitorOut,
)
from app.schemas.event import EventOut
from app.schemas.privacy import RemovalRequestListOut, RemovalRequestOut
from app.services import admin_stats, events as event_svc

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/events", response_model=PaginatedAdminEvents)
async def admin_list_events(
    page: int = 1,
    page_size: int = 20,
    # alias="status" so the query param is ?status=, following the same
    # pattern as admin_list_removal_requests below (avoids shadowing the
    # `status` module import).
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> PaginatedAdminEvents:
    """Paginated event list with photo_count/storage_used_bytes/last_activity_at
    (REQ-1, design D1) — one aggregated query, not N+1. Supports ?status= filter
    and ?sort=last_activity|photo_count.
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    rows, total = await admin_stats.list_events_with_stats(
        db, page, page_size, status_filter=status_filter, sort=sort
    )
    items = [
        AdminEventListItem(
            **EventOut.model_validate(event).model_dump(),
            photo_count=photo_count,
            storage_used_bytes=storage_used_bytes,
            last_activity_at=last_activity_at,
        )
        for event, photo_count, storage_used_bytes, last_activity_at in rows
    ]
    return PaginatedAdminEvents(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/events/{event_id}", response_model=AdminEventDetailOut)
async def admin_get_event_detail(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminEventDetailOut:
    """Event detail: context fields (D1) + processing monitor breakdown (D3).

    Backs the admin event detail view (REQ-2, REQ-4a/4b).
    """
    stats = await admin_stats.get_event_with_stats(db, event_id)
    if stats is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    event, photo_count, storage_used_bytes, last_activity_at = stats
    monitor = await admin_stats.get_processing_monitor(db, event_id)
    return AdminEventDetailOut(
        **EventOut.model_validate(event).model_dump(),
        photo_count=photo_count,
        storage_used_bytes=storage_used_bytes,
        last_activity_at=last_activity_at,
        processing_monitor=ProcessingMonitorOut(**monitor),
    )


@router.get("/health", response_model=PlatformHealthOut)
async def admin_platform_health(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> PlatformHealthOut:
    """Platform-wide health dashboard (REQ-7a/7b, design D6). Batch queries,
    no caching — computed fresh on every request."""
    health = await admin_stats.get_platform_health(db)
    return PlatformHealthOut(**health)


@router.post("/events/{event_id}/suspend", response_model=EventOut)
async def admin_suspend_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> EventOut:
    event = await event_svc.get_event(db, event_id)
    if event is None or event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    from datetime import datetime, timezone
    event.status = "suspended"
    event.updated_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/events/{event_id}/unsuspend", response_model=EventOut)
async def admin_unsuspend_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> EventOut:
    event = await event_svc.get_event(db, event_id)
    if event is None or event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    from datetime import datetime, timezone
    event.status = "published"
    event.updated_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return EventOut.model_validate(event)


@router.get("/removal-requests", response_model=RemovalRequestListOut)
async def admin_list_removal_requests(
    # Use alias="status" so the query param is ?status=pending (not ?status_filter=).
    # The variable is named status_filter to avoid shadowing the `status` import.
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RemovalRequestListOut:
    """List removal requests; optional ?status=pending filter.

    Also returns pending_count to power the dashboard badge (D6).
    """
    stmt = select(RemovalRequest).order_by(RemovalRequest.submitted_at.desc())
    if status_filter is not None:
        stmt = stmt.where(RemovalRequest.status == status_filter)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    # Pending count is always the total regardless of filter (for badge).
    pending_result = await db.execute(
        select(func.count()).select_from(RemovalRequest).where(
            RemovalRequest.status == "pending"
        )
    )
    pending_count = pending_result.scalar_one()

    return RemovalRequestListOut(
        items=[RemovalRequestOut.model_validate(r) for r in items],
        pending_count=pending_count,
    )


@router.post(
    "/removal-requests/{request_id}/fulfill",
    response_model=RemovalRequestOut,
)
async def admin_fulfill_removal_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RemovalRequestOut:
    """Mark a removal request as fulfilled (REQ-15, AC-4a).

    The record is NEVER deleted (REQ-16, AC-4b). Sets status='fulfilled'
    and records fulfilled_at timestamp.
    """
    result = await db.execute(
        select(RemovalRequest).where(RemovalRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Removal request not found",
        )
    req.status = "fulfilled"
    req.fulfilled_at = datetime.now(timezone.utc)
    db.add(req)
    await db.flush()
    await db.refresh(req)
    return RemovalRequestOut.model_validate(req)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_hard_delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    """Hard delete — same cascade as purge job, no grace period."""
    import shutil
    from pathlib import Path
    from app.config import settings as app_settings
    from app.services import qdrant

    event = await event_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # 1. Delete files from storage
    event_path = Path(app_settings.STORAGE_PATH) / "events" / str(event_id)
    if event_path.exists():
        shutil.rmtree(event_path)

    # 2. Delete the event's Qdrant collection (idempotent — REQ-3a/D2)
    qdrant.delete_collection(event_id)

    # 3. Hard delete from DB using the request session (keeps test DB consistent)
    await db.delete(event)
    await db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
