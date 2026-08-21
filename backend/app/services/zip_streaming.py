"""Streaming ZIP generation — zero full-buffer memory accumulation."""
import io
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

from app.config import settings
from app.services.gallery import _resolve_downloadable


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


def generate_zip_stream(photos: list, event_id: uuid.UUID) -> Iterator[bytes]:
    """Yield compressed ZIP bytes incrementally. Peak memory = max(single photo size).

    Each photo's downloadable path/filename is resolved via
    `gallery._resolve_downloadable` before being written into the archive,
    so a HEIC/HEIF original never ends up in the ZIP — it's transparently
    swapped for a cached JPEG conversion (extension included). See
    docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
    """
    storage_root = Path(settings.STORAGE_PATH).resolve()
    buf = _ZipBuffer()
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for photo in photos:
            resolved = _resolve_downloadable(
                storage_root, event_id, photo.id, photo.storage_path, photo.filename
            )
            if resolved is None:
                continue
            abs_path, download_filename = resolved
            base = download_filename
            if base in seen_names:
                seen_names[base] += 1
                stem, sep, ext = base.rpartition(".")
                arcname = f"{stem} ({seen_names[base]}).{ext}" if sep else f"{base} ({seen_names[base]})"
            else:
                seen_names[base] = 1
                arcname = base
            zf.write(str(abs_path), arcname=arcname)
            chunk = buf.pop()
            if chunk:
                yield chunk
    final = buf.pop()
    if final:
        yield final
