"""Photo upload and face-processing status endpoints."""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.schemas.photo import (
    FaceProcessingStatusResponse,
    PhotoUploadResponse,
    ProcessingStatusCounts,
)
from app.services.face_pipeline import process_photo

logger = logging.getLogger("weddinglens.photos")
router = APIRouter(prefix="/api/v1/events/{event_id}/photos", tags=["photos"])


async def _get_owned_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Event:
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.owner_id == current_user.id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.post("", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    event_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    event: Event = Depends(_get_owned_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoUploadResponse:
    photo_id = uuid.uuid4()
    relative_path = f"events/{event_id}/{photo_id}_{file.filename}"
    abs_path = Path(settings.STORAGE_PATH) / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    abs_path.write_bytes(contents)

    photo = Photo(
        id=photo_id,
        event_id=event_id,
        filename=file.filename or "upload",
        storage_path=relative_path,
        file_size=len(contents),
        processing_status="pending",
    )
    db.add(photo)
    await db.flush()  # get photo into DB before BackgroundTask runs

    background_tasks.add_task(process_photo, photo_id, event_id)

    return PhotoUploadResponse(
        id=photo.id,
        event_id=photo.event_id,
        filename=photo.filename,
        processing_status=photo.processing_status,
    )


# Separate router for the status endpoint (different URL prefix)
status_router = APIRouter(prefix="/api/v1/events", tags=["photos"])


@status_router.get(
    "/{event_id}/face-processing/status",
    response_model=FaceProcessingStatusResponse,
)
async def get_face_processing_status(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FaceProcessingStatusResponse:
    # Verify event is owned by current user
    event_result = await db.execute(
        select(Event).where(Event.id == event_id, Event.owner_id == current_user.id)
    )
    if event_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Count photos per status
    rows = await db.execute(
        select(Photo.processing_status, func.count(Photo.id))
        .where(Photo.event_id == event_id)
        .group_by(Photo.processing_status)
    )
    counts: dict[str, int] = {}
    for row_status, cnt in rows:
        counts[row_status] = cnt

    total = sum(counts.values())
    return FaceProcessingStatusResponse(
        event_id=event_id,
        total_photos=total,
        by_status=ProcessingStatusCounts(
            pending=counts.get("pending", 0),
            processing=counts.get("processing", 0),
            complete=counts.get("complete", 0),
            failed=counts.get("failed", 0),
            error=counts.get("error", 0),
        ),
    )
