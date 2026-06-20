"""Streaming ZIP generation — zero full-buffer memory accumulation."""
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

from app.config import settings


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
    __slots__ = ("storage_path", "filename")

    def __init__(self, storage_path: str, filename: str):
        self.storage_path = storage_path
        self.filename = filename


def generate_zip_stream(photos: list) -> Iterator[bytes]:
    """Yield compressed ZIP bytes incrementally. Peak memory = max(single photo size)."""
    storage_root = Path(settings.STORAGE_PATH).resolve()
    buf = _ZipBuffer()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for photo in photos:
            abs_path = (storage_root / photo.storage_path).resolve()
            if not abs_path.is_relative_to(storage_root) or not abs_path.exists():
                continue
            zf.write(str(abs_path), arcname=photo.filename)
            chunk = buf.pop()
            if chunk:
                yield chunk
    final = buf.pop()
    if final:
        yield final
