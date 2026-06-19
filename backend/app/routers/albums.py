"""Album management endpoints (owner JWT required)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.album import AlbumCreate, AlbumOut, AlbumUpdate
from app.services import albums as album_svc
from app.services import events as event_svc

router = APIRouter(prefix="/api/v1/events/{event_id}/albums", tags=["albums"])


async def _get_event_for_owner(
    event_id: uuid.UUID, db: AsyncSession, current_user: User
):
    event = await event_svc.get_event(db, event_id)
    if event is None or event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the event owner")
    return event


@router.get("", response_model=list[AlbumOut])
async def list_albums(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlbumOut]:
    await _get_event_for_owner(event_id, db, current_user)
    albums = await album_svc.list_albums(db, event_id)
    return [AlbumOut.model_validate(a) for a in albums]


@router.post("", response_model=AlbumOut, status_code=status.HTTP_201_CREATED)
async def create_album(
    event_id: uuid.UUID,
    data: AlbumCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlbumOut:
    await _get_event_for_owner(event_id, db, current_user)
    try:
        album = await album_svc.create_album(db, event_id, data)
    except album_svc.TooManyAlbumsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return AlbumOut.model_validate(album)


@router.put("/{album_id}", response_model=AlbumOut)
async def update_album(
    event_id: uuid.UUID,
    album_id: uuid.UUID,
    data: AlbumUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlbumOut:
    await _get_event_for_owner(event_id, db, current_user)
    album = await album_svc.get_album(db, event_id, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")
    album = await album_svc.update_album(db, album, data)
    return AlbumOut.model_validate(album)


@router.delete("/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album(
    event_id: uuid.UUID,
    album_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    await _get_event_for_owner(event_id, db, current_user)
    album = await album_svc.get_album(db, event_id, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")
    await album_svc.delete_album(db, album)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
