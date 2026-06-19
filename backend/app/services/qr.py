"""QR code generation service."""

import io

import qrcode
from qrcode.image.base import BaseImage

from app.config import settings


def generate_qr_png(slug: str) -> bytes:
    """
    Generate a QR code PNG for the given event slug.
    The QR payload is the public gallery URL: {FRONTEND_URL}/events/{slug}
    No file is written to disk — raw PNG bytes are returned.
    """
    url = f"{settings.FRONTEND_URL}/g/{slug}"
    img: BaseImage = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
