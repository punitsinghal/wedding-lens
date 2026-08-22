"""Streaming ZIP generation — zero full-buffer memory accumulation.

Photo bytes are fetched from Cloudflare R2 (not local disk) — see
docs/features/photo-storage-migration/design.md's "ZIP generation" section.
Because R2 fetches are network round-trips (much higher latency than the
local disk reads this replaced), photos are resolved concurrently via a
bounded `ThreadPoolExecutor` so the existing 30-second/100-photo bar
(REQ-15) still holds, rather than paying that latency once per photo in a
fully sequential loop.
"""
import io
import logging
import uuid
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from app.services import r2
from app.services.gallery import _convert_to_jpeg, _download_rel_path, _swap_ext_to_jpg
from app.services.image_format import sniff_image_format

logger = logging.getLogger("weddinglens.zip_streaming")

# Bounded worker count for concurrent per-photo R2 fetches. R2 GETs are
# network-latency-bound (not CPU-bound), so this can safely exceed the CPU
# count without contention concerns — it just needs to be high enough to hit
# REQ-15 (100 photos / <30s) and low enough to keep peak in-flight memory
# (one photo's bytes per worker) bounded. Not related to the 3-concurrent
# upload limit used elsewhere (that one is sized for face-pipeline/upload
# contention, which doesn't apply to read-only ZIP fetches).
_MAX_CONCURRENT_FETCHES = 8


class _ZipBuffer(io.RawIOBase):
    """File-like write target for zipfile.ZipFile that yields chunks on demand."""

    def __init__(self):
        self._pending = bytearray()
        self._total_written = 0

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        if isinstance(data, memoryview):
            data = bytes(data)
        self._pending.extend(data)
        self._total_written += len(data)
        return len(data)

    def tell(self) -> int:
        return self._total_written

    def pop(self) -> bytes:
        data = bytes(self._pending)
        self._pending.clear()
        return data


class Photo:
    """Minimal DTO used by generate_zip_stream — avoids importing ORM models here."""
    __slots__ = ("id", "storage_path", "filename")

    def __init__(self, id: uuid.UUID, storage_path: str, filename: str):
        self.id = id
        self.storage_path = storage_path
        self.filename = filename


def _resolve_for_zip(event_id: uuid.UUID, photo) -> tuple[str, bytes] | None:
    """Resolve one photo's `(arcname_base_filename, data_bytes)` for inclusion
    in a ZIP archive, fetching directly and synchronously from R2.

    Runs inside a `ThreadPoolExecutor` worker (see `generate_zip_stream`) —
    this whole module already executes in a thread (Starlette's
    `iterate_in_threadpool`, since `generate_zip_stream` is a sync
    generator), so R2 calls are made directly here rather than via
    `asyncio.to_thread`.

    Mirrors `gallery.get_downloadable_key`'s resolution logic (same
    JPEG/PNG-passthrough vs. HEIC/HEIF-conversion-with-cache behavior,
    same HEIC->JPEG conversion safety net — see
    docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md) but
    returns the photo's bytes directly instead of an R2 key, since a bulk
    ZIP has no single HTTP response to redirect to a presigned URL for.

    Returns None if the original is missing/unreadable — mirrors the
    previous local-disk behavior of skipping unresolvable photos rather
    than failing the whole ZIP.
    """
    try:
        header = r2.read_range(photo.storage_path, 0, 15)
    except r2.StorageUnavailableError:
        return None

    if sniff_image_format(header) in ("jpeg", "png"):
        return photo.filename, r2.download_object(photo.storage_path)

    download_key = _download_rel_path(event_id, photo.id)
    converted_filename = _swap_ext_to_jpg(photo.filename)

    original_bytes: bytes | None = None
    try:
        if r2.head_object(download_key):
            return converted_filename, r2.download_object(download_key)

        original_bytes = r2.download_object(photo.storage_path)
        jpeg_bytes = _convert_to_jpeg(original_bytes)
        r2.put_object(download_key, jpeg_bytes, "image/jpeg")
        return converted_filename, jpeg_bytes
    except Exception as exc:
        logger.warning(
            '{"event": "download_conversion_error", "photo_id": "%s", "exc_type": "%s", "detail": "%s"}',
            photo.id,
            type(exc).__name__,
            str(exc),
        )
        if original_bytes is not None:
            return photo.filename, original_bytes
        return None


def generate_zip_stream(photos: list, event_id: uuid.UUID) -> Iterator[bytes]:
    """Yield compressed ZIP bytes incrementally, fetching photo bytes from R2.

    A bounded pool of `_MAX_CONCURRENT_FETCHES` worker threads resolves
    photos (via `_resolve_for_zip`) concurrently, ahead of the point where
    each is written into the archive — `ThreadPoolExecutor.map()` yields
    results in input order, blocking only if a given result isn't ready
    yet, which gives "prefetch ahead, consume/write in order" without a
    hand-rolled sliding window. This keeps the existing per-photo output
    ordering and duplicate-filename numbering unchanged while absorbing
    R2's network latency (REQ-15: 100 photos in under 30 seconds).

    Peak memory is bounded by `_MAX_CONCURRENT_FETCHES` in-flight photos'
    worth of bytes (not by the total photo count, still consistent with
    REQ-14/NFR-5's "no full in-memory buffering" guarantee) — a different,
    but still bounded-regardless-of-count, bound than the old local-disk
    version's small read-buffer.
    """
    buf = _ZipBuffer()
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_FETCHES) as executor:
            results = executor.map(lambda photo: _resolve_for_zip(event_id, photo), photos)
            for resolved in results:
                if resolved is None:
                    continue
                base, data = resolved
                if base in seen_names:
                    seen_names[base] += 1
                    stem, sep, ext = base.rpartition(".")
                    arcname = f"{stem} ({seen_names[base]}).{ext}" if sep else f"{base} ({seen_names[base]})"
                else:
                    seen_names[base] = 1
                    arcname = base
                zf.writestr(arcname, data)
                chunk = buf.pop()
                if chunk:
                    yield chunk
    final = buf.pop()
    if final:
        yield final
