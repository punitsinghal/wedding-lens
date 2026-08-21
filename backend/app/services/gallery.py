"""Gallery service — photo listing, album tab counts, and derived image assets."""

import asyncio
import io
import logging
import uuid
from pathlib import Path

import pillow_heif
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.album import Album, CEREMONY_CATEGORIES
from app.models.photo import Photo
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


async def get_thumbnail_path(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> Path | None:
    """Resolve a safe absolute thumbnail file path for a photo, or None if
    the photo/thumbnail doesn't exist or the resolved path escapes storage."""
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None or photo.thumbnail_path is None:
        return None

    storage_root = Path(settings.STORAGE_PATH).resolve()
    abs_path = (storage_root / photo.thumbnail_path).resolve()
    if not abs_path.is_relative_to(storage_root) or not abs_path.exists():
        return None
    return abs_path


def _preview_rel_path(event_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    """Deterministic, DB-free cache path for a photo's lightbox preview.

    Derived purely from event_id/photo_id (mirrors the `thumbs/` convention
    used by face_pipeline._generate_thumbnail) so no new DB column or
    backfill migration is required — see ADR
    2026-08-21-lazy-generated-photo-preview-tier.md.
    """
    return f"events/{event_id}/previews/{photo_id}.webp"


def _generate_preview(image_bytes: bytes, abs_path: Path) -> None:
    """Generate a medium-resolution WebP preview for the lightbox and save it
    to `abs_path`. Longest edge is capped at PREVIEW_MAX_EDGE px; smaller
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

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a unique temp file then atomically rename into place, so a
    # concurrent request that hits the cache mid-write always sees either
    # nothing (falls through to the read-original path below) or a complete
    # file — never a partially-written one.
    tmp_path = abs_path.with_name(f".{abs_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        img.save(tmp_path, "WEBP", quality=90)
        tmp_path.replace(abs_path)
    finally:
        tmp_path.unlink(missing_ok=True)


async def get_or_generate_preview_path(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> Path | None:
    """Resolve the absolute path of a photo's lightbox preview, generating
    and caching it from the original file on first request. Returns None if
    the photo/original doesn't exist or any resolved path escapes storage.

    See docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md.
    """
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        return None

    storage_root = Path(settings.STORAGE_PATH).resolve()

    abs_preview_path = (storage_root / _preview_rel_path(event_id, photo_id)).resolve()
    if not abs_preview_path.is_relative_to(storage_root):
        return None

    if abs_preview_path.exists():
        return abs_preview_path

    abs_original_path = (storage_root / photo.storage_path).resolve()
    if not abs_original_path.is_relative_to(storage_root) or not abs_original_path.exists():
        return None

    try:
        image_bytes = await asyncio.to_thread(abs_original_path.read_bytes)
        await asyncio.to_thread(_generate_preview, image_bytes, abs_preview_path)
    except Exception as exc:
        logger.warning(
            '{"event": "preview_generation_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return None

    if not abs_preview_path.exists():
        return None
    return abs_preview_path


def _download_rel_path(event_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    """Deterministic, DB-free cache path for a photo's converted-for-download
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


def _convert_to_jpeg(image_bytes: bytes, abs_path: Path) -> None:
    """Decode `image_bytes` (expected HEIC/HEIF, but works for anything
    Pillow can open) and save as a high-quality JPEG at `abs_path`. Applies
    the same EXIF-orientation fix used elsewhere in this module. Uses the
    same atomic temp-file+rename pattern as `_generate_preview`."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = abs_path.with_name(f".{abs_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        img.save(tmp_path, "JPEG", quality=DOWNLOAD_CONVERSION_JPEG_QUALITY)
        tmp_path.replace(abs_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _resolve_downloadable(
    storage_root: Path,
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    storage_path: str,
    filename: str,
) -> tuple[Path, str] | None:
    """Synchronous core of `get_downloadable_path` — no DB access, so it can
    also be called directly from the (thread-pool-executed, sync) ZIP
    streaming generator in `app/services/zip_streaming.py`.

    Returns `(absolute_path, filename_to_send)`, or None if the original file
    doesn't exist or any resolved path escapes storage. Already-JPEG/PNG
    originals are returned unchanged (never re-encoded — re-encoding a file
    that's already in a guest-safe format would degrade quality for no
    benefit). Anything else is treated as a HEIC/HEIF-or-unknown format that
    needs converting; on conversion failure, falls back to the original
    file/filename rather than failing the download outright.
    """
    abs_original_path = (storage_root / storage_path).resolve()
    if not abs_original_path.is_relative_to(storage_root) or not abs_original_path.exists():
        return None

    try:
        with abs_original_path.open("rb") as f:
            header = f.read(16)
    except OSError:
        return None

    if sniff_image_format(header) in ("jpeg", "png"):
        return abs_original_path, filename

    abs_download_path = (storage_root / _download_rel_path(event_id, photo_id)).resolve()
    if not abs_download_path.is_relative_to(storage_root):
        return abs_original_path, filename

    converted_filename = _swap_ext_to_jpg(filename)

    if abs_download_path.exists():
        return abs_download_path, converted_filename

    try:
        image_bytes = abs_original_path.read_bytes()
        _convert_to_jpeg(image_bytes, abs_download_path)
    except Exception as exc:
        logger.warning(
            '{"event": "download_conversion_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo_id,
            type(exc).__name__,
            str(exc),
        )
        return abs_original_path, filename

    if not abs_download_path.exists():
        return abs_original_path, filename

    return abs_download_path, converted_filename


async def get_downloadable_path(
    db: AsyncSession, event_id: uuid.UUID, photo_id: uuid.UUID
) -> tuple[Path, str] | None:
    """Resolve `(absolute_path, filename_to_send)` for a guest download
    (single-photo or ZIP), guaranteeing the result is never a raw
    HEIC/HEIF file. Returns None if the photo/original doesn't exist or any
    resolved path escapes storage.

    See docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
    """
    result = await db.execute(
        select(Photo).where(Photo.id == photo_id, Photo.event_id == event_id)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        return None

    storage_root = Path(settings.STORAGE_PATH).resolve()
    return await asyncio.to_thread(
        _resolve_downloadable, storage_root, event_id, photo_id, photo.storage_path, photo.filename
    )


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
