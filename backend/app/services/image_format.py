"""Shared image-format detection by magic bytes.

Used as the *authoritative* gate for accepting an upload — independent of
(and layered on top of) the client-supplied `Content-Type` header, which is
trivially spoofable. A client (or a third-party "HEIC to JPEG converter" app
that only renames the file without re-encoding it) can label a real HEIC
file as `Content-Type: image/jpeg` / `photo.jpg`; only the actual file bytes
tell the truth.

Also used to route already-stored files at download time: anything that
isn't genuinely JPEG/PNG by magic bytes is treated as needing conversion —
see `app/services/gallery.py::get_downloadable_path` and
docs/decisions/2026-08-21-heic-to-jpeg-conversion-for-downloads.md.
"""

from typing import Literal

JPEG_MAGIC = b"\xff\xd8"
PNG_MAGIC = b"\x89PNG"

ImageFormat = Literal["jpeg", "png", "unknown"]


def sniff_image_format(data: bytes) -> ImageFormat:
    """Detect an image's real format from its magic bytes.

    Only distinguishes "known-safe" (jpeg/png) from everything else —
    callers that need to further identify HEIC/HEIF specifically (e.g. to
    decide whether a Pillow-with-HEIF decode is worth attempting) should
    just treat "unknown" as "try to convert, fall back to original on
    failure" rather than branching on HEIC detection here.
    """
    if data[:2] == JPEG_MAGIC:
        return "jpeg"
    if data[:4] == PNG_MAGIC:
        return "png"
    return "unknown"


def is_allowed_upload_format(data: bytes) -> bool:
    """True if the sniffed format is an accepted upload format (JPEG/PNG)."""
    return sniff_image_format(data) in ("jpeg", "png")
