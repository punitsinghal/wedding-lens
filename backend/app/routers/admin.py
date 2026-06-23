"""Admin endpoints (is_admin JWT required)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_admin
from app.models.privacy import RemovalRequest
from app.models.user import User
from app.schemas.event import EventOut, PaginatedEvents
from app.schemas.privacy import RemovalRequestListOut, RemovalRequestOut
from app.services import events as event_svc

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/events", response_model=PaginatedEvents)
async def admin_list_events(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> PaginatedEvents:
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    events, total = await event_svc.list_events_paginated(db, page, page_size)
    return PaginatedEvents(
        items=[EventOut.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
    )


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
    from app.services.purge import _stub_qdrant_delete

    event = await event_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # 1. Delete files from storage
    event_path = Path(app_settings.STORAGE_PATH) / "events" / str(event_id)
    if event_path.exists():
        shutil.rmtree(event_path)

    # 2. Stub Qdrant deletion
    _stub_qdrant_delete(event_id)

    # 3. Hard delete from DB using the request session (keeps test DB consistent)
    await db.delete(event)
    await db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
