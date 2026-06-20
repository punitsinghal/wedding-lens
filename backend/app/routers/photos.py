"""Photo upload and face-processing status endpoints."""
import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.album import Album
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.schemas.photo import (
    FaceProcessingStatusResponse,
    PhotoAlbumPatch,
    PhotoListResponse,
    PhotoOut,
    PhotoUploadResponse,
    ProcessingStatusCounts,
)
from app.services.face_pipeline import process_photo

logger = logging.getLogger("weddinglens.photos")
router = APIRouter(prefix="/api/v1/events/{event_id}/photos", tags=["photos"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


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


def _photo_to_out(photo: Photo, event_id: uuid.UUID) -> PhotoOut:
    thumbnail_url: str | None = None
    if photo.thumbnail_path is not None:
        thumbnail_url = f"/api/v1/events/{event_id}/photos/{photo.id}/preview"
    return PhotoOut(
        id=photo.id,
        event_id=photo.event_id,
        album_id=photo.album_id,
        filename=photo.filename,
        processing_status=photo.processing_status,
        thumbnail_url=thumbnail_url,
        created_at=photo.created_at,
    )


@router.post("", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    event_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    album_id: uuid.UUID | None = Form(None),
    event: Event = Depends(_get_owned_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoUploadResponse:
    photo_id = uuid.uuid4()
    relative_path = f"events/{event_id}/{photo_id}_{file.filename}"
    abs_path = Path(settings.STORAGE_PATH) / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Only JPEG and PNG files are accepted")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds the 25 MB limit")

    if album_id is not None:
        album_check = await db.execute(
            select(Album).where(Album.id == album_id, Album.event_id == event_id)
        )
        if album_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail="Album does not belong to this event")

    abs_path.write_bytes(contents)

    photo = Photo(
        id=photo_id,
        event_id=event_id,
        album_id=album_id,
        filename=file.filename or "upload",
        storage_path=relative_path,
        file_size=len(contents),
        processing_status="pending",
    )
    db.add(photo)
    try:
        await db.flush()  # get photo into DB before BackgroundTask runs
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Invalid album_id")

    background_tasks.add_task(process_photo, photo_id, event_id)

    return PhotoUploadResponse(
        id=photo.id,
        event_id=photo.event_id,
        album_id=photo.album_id,
        filename=photo.filename,
        processing_status=photo.processing_status,
    )


@router.get("", response_model=PhotoListResponse)
async def list_photos(
    event_id: uuid.UUID,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
    album_id: uuid.UUID | None = Query(None),
    event: Event = Depends(_get_owned_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoListResponse:
    count_q = select(func.count(Photo.id)).where(Photo.event_id == event_id)
    if album_id is not None:
        count_q = count_q.where(Photo.album_id == album_id)
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    rows_q = (
        select(Photo)
        .where(Photo.event_id == event_id)
        .order_by(Photo.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if album_id is not None:
        rows_q = rows_q.where(Photo.album_id == album_id)
    rows = await db.execute(rows_q)
    photos = list(rows.scalars().all())

    return PhotoListResponse(
        items=[_photo_to_out(p, event_id) for p in photos],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{photo_id}/album", response_model=PhotoOut)
async def update_photo_album(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotoAlbumPatch,
    event: Event = Depends(_get_owned_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoOut:
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    if body.album_id is not None:
        album_check = await db.execute(
            select(Album).where(Album.id == body.album_id, Album.event_id == event_id)
        )
        if album_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=422, detail="Album does not belong to this event")

    photo.album_id = body.album_id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Invalid album_id")
    await db.refresh(photo)

    return _photo_to_out(photo, event_id)


@router.get("/{photo_id}/preview")
async def get_photo_preview(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    event: Event = Depends(_get_owned_event),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    if photo.thumbnail_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    storage_root = Path(settings.STORAGE_PATH).resolve()
    abs_path = (storage_root / photo.thumbnail_path).resolve()
    if not abs_path.is_relative_to(storage_root):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found")

    media_type = mimetypes.guess_type(str(abs_path))[0] or "image/webp"
    return FileResponse(
        str(abs_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
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
