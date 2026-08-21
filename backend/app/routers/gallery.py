"""Gallery endpoints — photo browsing, thumbnails, downloads, photographer choice."""

import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_event_with_photographer_access, get_validated_guest_event
from app.models.event import Event
from app.models.photo import Photo
from app.schemas.gallery import (
    AlbumTabOut,
    GalleryListResponse,
    GalleryPhotoOut,
    PhotographerChoiceOut,
    PhotographerChoicePatch,
)
from app.services import analytics as analytics_service
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
        uploaded_by=photo.uploaded_by,
        guest_display_name=photo.guest_display_name,
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
    _event, refreshed_token, _sid = guest_event
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
    _event, refreshed_token, _sid = guest_event
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
    _event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    abs_path = await gallery_service.get_thumbnail_path(db, event_id, photo_id)
    if abs_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available"
        )

    media_type = mimetypes.guess_type(str(abs_path))[0] or "image/webp"
    return FileResponse(
        str(abs_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/photos/{photo_id}/lightbox")
async def get_lightbox_preview(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Medium-resolution (<=2000px) preview for the lightbox — generated
    lazily from the original on first request and cached to disk on subsequent
    requests. See docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md.

    Named `/lightbox` rather than `/preview` because
    `GET /api/v1/events/{event_id}/photos/{photo_id}/preview` already exists
    in app/routers/photos.py — a photographer-only endpoint (gated by
    get_event_with_photographer_access) that just re-serves the existing
    thumbnail_path for the dashboard's photo grid. That route has different
    auth and different bytes; reusing its path here would either collide
    (whichever router registers first in main.py wins, silently making the
    other dead code) or require changing that endpoint's guest-facing
    behavior, which is out of scope.
    """
    _event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    abs_path = await gallery_service.get_or_generate_preview_path(db, event_id, photo_id)
    if abs_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preview not available"
        )

    media_type = mimetypes.guess_type(str(abs_path))[0] or "image/webp"
    return FileResponse(
        str(abs_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/photos/{photo_id}/download")
async def download_photo(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    background_tasks: BackgroundTasks,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    _event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    storage_root = Path(settings.STORAGE_PATH).resolve()
    abs_path = (storage_root / photo.storage_path).resolve()
    if not abs_path.is_relative_to(storage_root):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not abs_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found"
        )

    # Atomically increment download count — only after confirming file exists
    await db.execute(
        update(Photo)
        .where(Photo.id == photo_id, Photo.event_id == event_id)
        .values(download_count=Photo.download_count + 1)
    )
    await db.commit()

    # D5/S6 — one download_events row per download action (fire-and-forget,
    # NFR-3). Separate from Photo.download_count above (per-photo badge,
    # unrelated purpose — see design D5's explicit note not to conflate them).
    background_tasks.add_task(analytics_service.record_download_event, event_id)

    return FileResponse(
        str(abs_path),
        media_type="application/octet-stream",
        filename=photo.filename,
    )


@router.post("/photos/{photo_id}/view", status_code=status.HTTP_204_NO_CONTENT)
async def record_photo_view(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    background_tasks: BackgroundTasks,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Guest photo-view beacon (S6, design D5). Fire-and-forget: the response
    returns 204 immediately regardless of whether the insert succeeds
    (NFR-3) — this is intentionally NOT gated on the photo actually existing,
    since a failed lookup must not fail the beacon either.
    """
    _event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    background_tasks.add_task(analytics_service.record_view_event, event_id)


@router.patch("/photos/{photo_id}/photographer-choice", response_model=PhotographerChoiceOut)
async def toggle_photographer_choice(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotographerChoicePatch,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> PhotographerChoiceOut:
    # Access is already verified by get_event_with_photographer_access (owner or assigned photographer)
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
