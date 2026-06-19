"""Album business logic."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.schemas.album import AlbumCreate, AlbumUpdate

MAX_ALBUMS_PER_EVENT = 10


async def list_albums(db: AsyncSession, event_id: uuid.UUID) -> list[Album]:
    result = await db.execute(
        select(Album)
        .where(Album.event_id == event_id)
        .order_by(Album.sort_order, Album.created_at)
    )
    return list(result.scalars().all())


async def get_album(
    db: AsyncSession, event_id: uuid.UUID, album_id: uuid.UUID
) -> Album | None:
    result = await db.execute(
        select(Album).where(Album.id == album_id, Album.event_id == event_id)
    )
    return result.scalar_one_or_none()


async def create_album(
    db: AsyncSession, event_id: uuid.UUID, data: AlbumCreate
) -> Album:
    count_result = await db.execute(
        select(func.count()).select_from(Album).where(Album.event_id == event_id)
    )
    count = count_result.scalar_one()
    if count >= MAX_ALBUMS_PER_EVENT:
        raise TooManyAlbumsError(f"Events may have at most {MAX_ALBUMS_PER_EVENT} albums")

    album = Album(
        id=uuid.uuid4(),
        event_id=event_id,
        name=data.name,
        ceremony_category=data.ceremony_category,
        sort_order=data.sort_order,
    )
    db.add(album)
    await db.flush()
    return album


async def update_album(
    db: AsyncSession, album: Album, data: AlbumUpdate
) -> Album:
    if data.name is not None:
        album.name = data.name
    if data.ceremony_category is not None:
        album.ceremony_category = data.ceremony_category
    if data.sort_order is not None:
        album.sort_order = data.sort_order
    album.updated_at = datetime.now(timezone.utc)
    db.add(album)
    await db.flush()
    return album


async def delete_album(db: AsyncSession, album: Album) -> None:
    # Photos referencing this album are set to uncategorized (album_id = NULL).
    # Since the photos table does not exist in this epic, the FK cascade from
    # photos to albums will be handled when that epic is implemented.
    # The delete here only removes the album record itself.
    await db.delete(album)
    await db.flush()


class TooManyAlbumsError(Exception):
    pass
