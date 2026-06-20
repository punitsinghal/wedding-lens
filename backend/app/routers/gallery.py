"""Gallery endpoints — photo browsing, thumbnails, downloads, photographer choice."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, get_validated_guest_event
from app.models.event import Event
from app.models.photo import Photo
from app.models.user import User
from app.schemas.gallery import (
    AlbumTabOut,
    GalleryListResponse,
    GalleryPhotoOut,
    PhotographerChoiceOut,
    PhotographerChoicePatch,
)
from app.services import gallery as gallery_service

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["gallery"])


def _photo_to_out(photo: Photo, event_id: uuid.UUID) -> GalleryPhotoOut:
    thumbnail_url: str | None = None
    if photo.thumbnail_path is not None:
        thumbnail_url = f"/api/v1/events/{event_id}/photos/{photo.id}/thumbnail"
    return GalleryPhotoOut(
        id=photo.id,
        thumbnail_url=thumbnail_url,
        is_photographer_choice=photo.is_photographer_choice,
        download_count=photo.download_count,
        created_at=photo.created_at,
    )


@router.get("/gallery", response_model=GalleryListResponse)
async def list_gallery(
    event_id: uuid.UUID,
    response: Response,
    album: str | None = None,
    sort: str = "latest",
    limit: int = Query(default=50, le=50),
    offset: int = 0,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> GalleryListResponse:
    _event, refreshed_token = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    photos, total = await gallery_service.list_photos(
        db, event_id, album, sort, limit, offset
    )
    return GalleryListResponse(
        photos=[_photo_to_out(p, event_id) for p in photos],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/gallery/albums", response_model=list[AlbumTabOut])
async def list_gallery_albums(
    event_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> list[AlbumTabOut]:
    _event, refreshed_token = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    tabs = await gallery_service.list_album_tabs(db, event_id)
    return [AlbumTabOut(**tab) for tab in tabs]


@router.get("/photos/{photo_id}/thumbnail")
async def get_thumbnail(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    _event, refreshed_token = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    if photo.thumbnail_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available"
        )

    abs_path = Path(settings.STORAGE_PATH) / photo.thumbnail_path
    if not abs_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found"
        )

    return FileResponse(
        str(abs_path),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/photos/{photo_id}/download")
async def download_photo(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    _event, refreshed_token = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # Atomically increment download count
    await db.execute(
        update(Photo)
        .where(Photo.id == photo_id, Photo.event_id == event_id)
        .values(download_count=Photo.download_count + 1)
    )
    await db.commit()

    abs_path = Path(settings.STORAGE_PATH) / photo.storage_path
    if not abs_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found"
        )

    return FileResponse(
        str(abs_path),
        media_type="application/octet-stream",
        filename=photo.filename,
        headers={"Content-Disposition": f"attachment; filename={photo.filename}"},
    )


@router.patch("/photos/{photo_id}/photographer-choice", response_model=PhotographerChoiceOut)
async def toggle_photographer_choice(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotographerChoicePatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotographerChoiceOut:
    # Verify event ownership
    event_result = await db.execute(
        select(Event).where(Event.id == event_id, Event.owner_id == current_user.id)
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    await db.execute(
        update(Photo)
        .where(Photo.id == photo_id, Photo.event_id == event_id)
        .values(is_photographer_choice=body.is_photographer_choice)
    )
    await db.commit()

    return PhotographerChoiceOut(is_photographer_choice=body.is_photographer_choice)
