"""SSE-based real-time face-processing progress stream for the photographer dashboard."""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.dependencies import get_current_user_from_query_token
from app.models.assignment import EventPhotographer
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User

logger = logging.getLogger("weddinglens.progress")

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["progress"])

MAX_ITERATIONS = 30  # 60 seconds at 2s intervals


@router.get("/progress")
async def get_progress(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user_from_query_token),
):
    """
    SSE stream of face-processing progress for an event.
    Auth: JWT passed as ?token= query param (EventSource cannot set Authorization headers).
    Emits 'progress' events every 2 seconds; emits 'gallery_ready' and closes when done.
    """
    # Access check: owner or assigned photographer
    async with AsyncSessionLocal() as db:
        event_result = await db.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        if event is None or event.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

        if event.owner_id != current_user.id:
            assignment_result = await db.execute(
                select(EventPhotographer).where(
                    EventPhotographer.event_id == event_id,
                    EventPhotographer.photographer_id == current_user.id,
                )
            )
            if assignment_result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: not the event owner or an assigned photographer",
                )

    async def event_stream():
        for _ in range(MAX_ITERATIONS):
            async with AsyncSessionLocal() as db:
                rows = await db.execute(
                    select(Photo.processing_status, func.count(Photo.id))
                    .where(Photo.event_id == event_id)
                    .group_by(Photo.processing_status)
                )
                counts = {r[0]: r[1] for r in rows}

            total = sum(counts.values())
            indexed = counts.get("complete", 0)
            pending = counts.get("pending", 0) + counts.get("processing", 0)
            failed = counts.get("failed", 0) + counts.get("error", 0)

            data = json.dumps(
                {"total": total, "indexed": indexed, "pending": pending, "failed": failed}
            )
            yield f"event: progress\ndata: {data}\n\n"

            if total > 0 and pending == 0:
                yield f"event: gallery_ready\ndata: {data}\n\n"
                return

            await asyncio.sleep(2)

        # Send a keepalive comment before client must reconnect
        yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
