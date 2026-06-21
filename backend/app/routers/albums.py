"""Album management endpoints (owner or assigned photographer JWT required)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_event_with_photographer_access
from app.models.event import Event
from app.schemas.album import AlbumCreate, AlbumOut, AlbumUpdate
from app.services import albums as album_svc

router = APIRouter(prefix="/api/v1/events/{event_id}/albums", tags=["albums"])


@router.get("", response_model=list[AlbumOut])
async def list_albums(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    event: Event = Depends(get_event_with_photographer_access),
) -> list[AlbumOut]:
    albums = await album_svc.list_albums(db, event_id)
    return [AlbumOut.model_validate(a) for a in albums]


@router.get("/{album_id}", response_model=AlbumOut)
async def get_album(
    event_id: uuid.UUID,
    album_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    event: Event = Depends(get_event_with_photographer_access),
) -> AlbumOut:
    album = await album_svc.get_album(db, event_id, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")
    return AlbumOut.model_validate(album)


@router.post("", response_model=AlbumOut, status_code=status.HTTP_201_CREATED)
async def create_album(
    event_id: uuid.UUID,
    data: AlbumCreate,
    db: AsyncSession = Depends(get_db),
    event: Event = Depends(get_event_with_photographer_access),
) -> AlbumOut:
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
    event: Event = Depends(get_event_with_photographer_access),
) -> AlbumOut:
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
    event: Event = Depends(get_event_with_photographer_access),
) -> Response:
    album = await album_svc.get_album(db, event_id, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")
    await album_svc.delete_album(db, album)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
