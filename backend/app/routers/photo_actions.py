"""Photo action endpoints — ZIP download, share link, favourites CRUD."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_validated_guest_event
from app.models.photo import Photo
from app.services.favourites_store import favourites_store
from app.services.guest_auth import create_share_token
from app.services.zip_streaming import generate_zip_stream

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["photo-actions"])

_ZIP_PHOTO_CAP = 200
_FAVOURITES_CAP = 500


@router.post("/photos/zip", status_code=200)
async def bulk_zip_download(
    event_id: uuid.UUID,
    response: Response,
    photo_ids: Annotated[list[uuid.UUID], Body(embed=True)],
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
):
    event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    if not photo_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="photo_ids_required")

    # Cap at 200 and deduplicate to prevent false 403
    photo_ids = list(dict.fromkeys(photo_ids[:_ZIP_PHOTO_CAP]))

    # Validate all IDs belong to this event in one query
    result = await db.execute(
        select(Photo.id).where(
            Photo.id.in_(photo_ids),
            Photo.event_id == event_id,
        )
    )
    found_ids = {row[0] for row in result.all()}
    if len(found_ids) != len(photo_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="photo_not_in_event")

    # Fetch storage details in request order
    result2 = await db.execute(
        select(Photo.id, Photo.storage_path, Photo.filename).where(
            Photo.id.in_(photo_ids),
            Photo.event_id == event_id,
        )
    )
    rows = {row.id: row for row in result2.all()}
    photos_ordered = [rows[pid] for pid in photo_ids if pid in rows]

    zip_filename = f"wedding-{event.slug}-my-photos.zip"

    return StreamingResponse(
        generate_zip_stream(photos_ordered),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "X-Guest-Token": refreshed_token,
        },
    )


@router.post("/photos/{photo_id}/share", status_code=status.HTTP_201_CREATED)
async def generate_share_link(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event, refreshed_token, _sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    result = await db.execute(
        select(Photo.id).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="photo_not_in_event")

    token = create_share_token(str(photo_id), str(event_id))
    share_url = f"{settings.APP_HOST}/share/{token}"

    expires_at = datetime.now(timezone.utc) + timedelta(hours=72)

    return {
        "share_url": share_url,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/favourites")
async def list_favourites(
    event_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    photo_ids = favourites_store.get(sid)
    if not photo_ids:
        return {"photos": []}

    result = await db.execute(
        select(Photo.id, Photo.thumbnail_path).where(
            Photo.id.in_([uuid.UUID(pid) for pid in photo_ids]),
            Photo.event_id == event_id,
        )
    )
    photos = []
    for row in result.all():
        thumbnail_url = f"/api/v1/events/{event_id}/photos/{row.id}/thumbnail" if row.thumbnail_path else None
        photos.append({"photo_id": str(row.id), "thumbnail_url": thumbnail_url})

    return {"photos": photos}


@router.put("/favourites/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favourite(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> None:
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    result = await db.execute(
        select(Photo.id).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    if len(favourites_store.get(sid)) >= _FAVOURITES_CAP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="favourites_cap_reached")

    favourites_store.add(sid, str(photo_id))


@router.delete("/favourites/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favourite(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> None:
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    favourites_store.remove(sid, str(photo_id))


@router.post("/favourites/zip", status_code=200)
async def favourites_zip_download(
    event_id: uuid.UUID,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
):
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    photo_id_strs = favourites_store.get(sid)
    if not photo_id_strs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_favourites")

    photo_ids = [uuid.UUID(pid) for pid in photo_id_strs]
    photo_ids = photo_ids[:_ZIP_PHOTO_CAP]

    # Validate all belong to this event
    result = await db.execute(
        select(Photo.id).where(Photo.id.in_(photo_ids), Photo.event_id == event_id)
    )
    found_ids = {row[0] for row in result.all()}
    invalid = [pid for pid in photo_ids if pid not in found_ids]
    if invalid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="photo_not_in_event")

    # Fetch in order
    result2 = await db.execute(
        select(Photo.id, Photo.storage_path, Photo.filename).where(
            Photo.id.in_(photo_ids),
            Photo.event_id == event_id,
        )
    )
    rows = {row.id: row for row in result2.all()}
    photos_ordered = [rows[pid] for pid in photo_ids if pid in rows]

    zip_filename = f"wedding-{event.slug}-my-favourites.zip"

    return StreamingResponse(
        generate_zip_stream(photos_ordered),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "X-Guest-Token": refreshed_token,
        },
    )
