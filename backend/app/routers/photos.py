"""Photo upload and face-processing status endpoints."""
from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, get_event_with_photographer_access
from app.models.album import Album
from app.models.event import Event
from app.models.photo import Photo, PhotoAlbum
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


# ---------------------------------------------------------------------------
# Additional request schemas
# ---------------------------------------------------------------------------


class PhotoAlbumsPut(BaseModel):
    album_ids: list[uuid.UUID] = []


class PhotoAlbumsOut(BaseModel):
    photo_id: uuid.UUID
    album_ids: list[uuid.UUID]


class ReprocessOut(BaseModel):
    photo_id: uuid.UUID
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    event_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    album_id: uuid.UUID | None = Form(None),
    event: Event = Depends(get_event_with_photographer_access),
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
    if album_id is not None:
        db.add(PhotoAlbum(photo_id=photo_id, album_id=album_id))
    try:
        await db.commit()
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
    event: Event = Depends(get_event_with_photographer_access),
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
    event: Event = Depends(get_event_with_photographer_access),
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

    # Sync photo_albums join table
    await db.execute(delete(PhotoAlbum).where(PhotoAlbum.photo_id == photo_id))
    if body.album_id is not None:
        db.add(PhotoAlbum(photo_id=photo_id, album_id=body.album_id))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Invalid album_id")
    await db.refresh(photo)

    return _photo_to_out(photo, event_id)


@router.put("/{photo_id}/albums", response_model=PhotoAlbumsOut)
async def set_photo_albums(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotoAlbumsPut,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> PhotoAlbumsOut:
    """Replace all album assignments for a photo (many-to-many)."""
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # Validate all album_ids belong to this event
    if body.album_ids:
        albums_result = await db.execute(
            select(Album).where(
                Album.id.in_(body.album_ids),
                Album.event_id == event_id,
            )
        )
        found_albums = {a.id for a in albums_result.scalars().all()}
        missing = set(body.album_ids) - found_albums
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Album IDs do not belong to this event: {[str(a) for a in missing]}",
            )

    # Delete all existing photo_albums for this photo
    await db.execute(delete(PhotoAlbum).where(PhotoAlbum.photo_id == photo_id))

    # Insert new entries
    for alb_id in body.album_ids:
        db.add(PhotoAlbum(photo_id=photo_id, album_id=alb_id))

    # Sync denormalized album_id (first album or None) for backward compat
    photo.album_id = body.album_ids[0] if body.album_ids else None

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Invalid album assignment")

    return PhotoAlbumsOut(photo_id=photo_id, album_ids=body.album_ids)


@router.post("/{photo_id}/reprocess", response_model=ReprocessOut, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_photo(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> ReprocessOut:
    """Re-enqueue face processing for a failed photo."""
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    if photo.processing_status not in ("failed", "error"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Photo is not in a failed state (current: {photo.processing_status})",
        )

    photo.processing_status = "pending"
    photo.face_error = None
    photo.processing_attempts = 0
    await db.commit()

    background_tasks.add_task(process_photo, photo_id, event_id)

    return ReprocessOut(photo_id=photo_id, status="pending")


@router.get("/{photo_id}/preview")
async def get_photo_preview(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    event: Event = Depends(get_event_with_photographer_access),
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


# ---------------------------------------------------------------------------
# Separate router for the status endpoint (different URL prefix)
# ---------------------------------------------------------------------------

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
