"""Gallery service — photo listing, album tab counts, and derived image assets.

Photo bytes (originals, thumbnails, previews, HEIC-conversion downloads) live
in Cloudflare R2, addressed by key — not on local disk — so there is no
filesystem path-escape concern here (an R2 key is just a string passed to an
API call, not something that can traverse outside a root directory). See
docs/features/photo-storage-migration/design.md.
"""

import asyncio
import io
import logging
import uuid

import pillow_heif
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album, CEREMONY_CATEGORIES
from app.models.photo import Photo
from app.services import r2
from app.services.image_format import sniff_image_format

logger = logging.getLogger("weddinglens.gallery")

# Registers the HEIF/HEIC opener with Pillow once, at import time, so
# `PIL.Image.open` can decode HEIC/HEIF bytes anywhere in this module. See
# docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
pillow_heif.register_heif_opener()

# Fixed display order for ceremony categories
_CATEGORY_ORDER = list(CEREMONY_CATEGORIES)

# Longest edge, in pixels, for the lightbox "preview" tier — see
# docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md
PREVIEW_MAX_EDGE = 2000

# JPEG quality for the download-time HEIC->JPEG conversion safety net. Kept
# high (this is a format-compatibility conversion, not a size optimization —
# see docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md,
# and the prior quality-degradation lesson in
# docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md about not
# re-encoding originals that don't need it).
DOWNLOAD_CONVERSION_JPEG_QUALITY = 95


async def get_thumbnail_key(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> str | None:
    """Return the photo's thumbnail R2 key, or None if the photo doesn't
    exist or has no thumbnail recorded.

    Pure DB lookup — deliberately does NOT `head_object` R2 to confirm the
    object actually exists there, since this is called once per photo in a
    gallery batch (up to 50 per page load) and that network round-trip cost
    matters at that volume. If the DB column is set but the object is
    missing in R2, the client's request against the resulting presigned URL
    simply fails — an acceptable, rare edge case.
    """
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None or photo.thumbnail_path is None:
        return None
    return photo.thumbnail_path


def _preview_rel_path(event_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    """Deterministic, DB-free cache key for a photo's lightbox preview.

    Derived purely from event_id/photo_id (mirrors the `thumbs/` convention
    used by face_pipeline._generate_thumbnail) so no new DB column or
    backfill migration is required — see ADR
    2026-08-21-lazy-generated-photo-preview-tier.md.
    """
    return f"events/{event_id}/previews/{photo_id}.webp"


def _generate_preview(image_bytes: bytes) -> bytes:
    """Generate a medium-resolution WebP preview for the lightbox and return
    its bytes. Longest edge is capped at PREVIEW_MAX_EDGE px; smaller
    originals are never upscaled. Mirrors the EXIF-orientation fix used by
    face_pipeline._generate_thumbnail so previews aren't rendered sideways."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    longest = max(w, h)
    if longest > PREVIEW_MAX_EDGE:
        scale = PREVIEW_MAX_EDGE / longest
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    # else: original is already <= PREVIEW_MAX_EDGE on its longest edge —
    # never upscale.

    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=90)
    return buf.getvalue()


async def get_or_generate_preview_key(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> str | None:
    """Resolve the R2 key of a photo's lightbox preview, generating and
    caching it from the original on first request. Returns None if the
    photo/original doesn't exist or generation fails for any reason.

    See docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md.
    """
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        return None

    preview_key = _preview_rel_path(event_id, photo_id)

    try:
        if await asyncio.to_thread(r2.head_object, preview_key):
            return preview_key
    except r2.StorageUnavailableError as exc:
        logger.warning(
            '{"event": "preview_head_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return None

    try:
        image_bytes = await asyncio.to_thread(r2.download_object, photo.storage_path)
    except r2.StorageUnavailableError as exc:
        logger.warning(
            '{"event": "preview_generation_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return None

    try:
        preview_bytes = await asyncio.to_thread(_generate_preview, image_bytes)
        await asyncio.to_thread(r2.put_object, preview_key, preview_bytes, "image/webp")
    except Exception as exc:
        logger.warning(
            '{"event": "preview_generation_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return None

    return preview_key


def _download_rel_path(event_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    """Deterministic, DB-free cache key for a photo's converted-for-download
    JPEG. Mirrors `_preview_rel_path` — no new DB column or backfill
    migration required. See
    docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
    """
    return f"events/{event_id}/downloads/{photo_id}.jpg"


def _swap_ext_to_jpg(filename: str) -> str:
    """Swap a filename's extension for `.jpg` (e.g. `IMG_4521.HEIC` ->
    `IMG_4521.jpg`), so a converted download isn't sent with a mismatched
    extension. Filenames with no extension get `.jpg` appended."""
    stem, sep, _ext = filename.rpartition(".")
    return f"{stem}.jpg" if sep else f"{filename}.jpg"


def _convert_to_jpeg(image_bytes: bytes) -> bytes:
    """Decode `image_bytes` (expected HEIC/HEIF, but works for anything
    Pillow can open) and return it re-encoded as a high-quality JPEG.
    Applies the same EXIF-orientation fix used elsewhere in this module."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=DOWNLOAD_CONVERSION_JPEG_QUALITY)
    return buf.getvalue()


async def get_downloadable_key(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> tuple[str, str] | None:
    """Resolve `(r2_key, filename_to_send)` for a guest download
    (single-photo), guaranteeing the result is never a raw HEIC/HEIF file.
    Returns None if the photo/original doesn't exist or storage is
    unavailable. Already-JPEG/PNG originals are returned unchanged (never
    re-encoded). Anything else is treated as HEIC/HEIF-or-unknown and
    converted, cached, lazily.

    See docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
    """
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        return None

    try:
        header = await asyncio.to_thread(r2.read_range, photo.storage_path, 0, 15)
    except r2.StorageUnavailableError:
        return None

    if sniff_image_format(header) in ("jpeg", "png"):
        return photo.storage_path, photo.filename

    download_key = _download_rel_path(event_id, photo_id)
    converted_filename = _swap_ext_to_jpg(photo.filename)

    try:
        if await asyncio.to_thread(r2.head_object, download_key):
            return download_key, converted_filename

        image_bytes = await asyncio.to_thread(r2.download_object, photo.storage_path)
        jpeg_bytes = await asyncio.to_thread(_convert_to_jpeg, image_bytes)
        await asyncio.to_thread(r2.put_object, download_key, jpeg_bytes, "image/jpeg")
    except Exception as exc:
        logger.warning(
            '{"event": "download_conversion_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return photo.storage_path, photo.filename

    return download_key, converted_filename


async def list_photos(
    db: AsyncSession,
    event_id: uuid.UUID,
    album: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[Photo], int]:
    """Returns (photos, total_count)."""

    # Show all photos regardless of processing_status — face data is orthogonal to
    # gallery browsing (OQ-5 decision: pending/failed photos show a thumbnail placeholder)
    base_q = select(Photo).where(Photo.event_id == event_id)

    if album is not None:
        # Join albums and filter by ceremony_category; exclude private albums
        base_q = base_q.join(Album, Photo.album_id == Album.id).where(
            Album.ceremony_category == album, Album.visibility == "public"
        )
    else:
        # Photos with no album are always visible; exclude photos in private albums
        base_q = base_q.outerjoin(Album, Photo.album_id == Album.id).where(
            or_(Photo.album_id.is_(None), Album.visibility == "public")
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
    # Total all photos for event → All tab count (exclude private album photos)
    total_result = await db.execute(
        select(func.count(Photo.id))
        .select_from(Photo)
        .outerjoin(Album, Photo.album_id == Album.id)
        .where(Photo.event_id == event_id)
        .where(or_(Photo.album_id.is_(None), Album.visibility == "public"))
    )
    total = total_result.scalar_one()

    tabs = [{"ceremony_category": None, "label": "All", "photo_count": total}]

    # Join photos → albums, group by ceremony_category, count; skip private albums
    rows_result = await db.execute(
        select(Album.ceremony_category, func.count(Photo.id))
        .join(Photo, Photo.album_id == Album.id)
        .where(Photo.event_id == event_id)
        .where(Album.ceremony_category.isnot(None))
        .where(Album.visibility == "public")
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
