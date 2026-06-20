"""Gallery service — photo listing and album tab counts."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album, CEREMONY_CATEGORIES
from app.models.photo import Photo

# Fixed display order for ceremony categories
_CATEGORY_ORDER = list(CEREMONY_CATEGORIES)


async def list_photos(
    db: AsyncSession,
    event_id: uuid.UUID,
    album: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[Photo], int]:
    """Returns (photos, total_count)."""

    base_q = select(Photo).where(Photo.event_id == event_id)

    if album is not None:
        # Join albums and filter by ceremony_category
        base_q = base_q.join(Album, Photo.album_id == Album.id).where(
            Album.ceremony_category == album
        )

    # Sorting
    if sort == "popular":
        base_q = base_q.order_by(Photo.download_count.desc())
    elif sort == "photographer-choice":
        base_q = base_q.order_by(
            Photo.is_photographer_choice.desc(), Photo.created_at.desc()
        )
    else:  # default: latest
        base_q = base_q.order_by(Photo.created_at.desc())

    # Count query (same filters, no limit/offset, no order)
    count_q = select(func.count()).select_from(base_q.order_by(None).subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # Paginated query
    paginated_q = base_q.limit(limit).offset(offset)
    result = await db.execute(paginated_q)
    photos = list(result.scalars().all())

    return photos, total


async def list_album_tabs(db: AsyncSession, event_id: uuid.UUID) -> list[dict]:
    """
    Returns the 'All' tab plus one tab per ceremony_category present in the event,
    with photo_count > 0 only.
    """
    # Total all photos for event → All tab count
    total_result = await db.execute(
        select(func.count(Photo.id)).where(Photo.event_id == event_id)
    )
    total = total_result.scalar_one()

    tabs = [{"ceremony_category": None, "label": "All", "photo_count": total}]

    # Join photos → albums, group by ceremony_category, count
    rows_result = await db.execute(
        select(Album.ceremony_category, func.count(Photo.id))
        .join(Photo, Photo.album_id == Album.id)
        .where(Photo.event_id == event_id)
        .where(Album.ceremony_category.isnot(None))
        .group_by(Album.ceremony_category)
    )
    category_counts: dict[str, int] = {}
    for category, count in rows_result:
        if count > 0:
            category_counts[category] = count

    # Add tabs in fixed global category order
    for category in _CATEGORY_ORDER:
        if category in category_counts:
            tabs.append(
                {
                    "ceremony_category": category,
                    "label": category,
                    "photo_count": category_counts[category],
                }
            )

    return tabs
