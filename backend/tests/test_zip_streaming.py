"""Unit tests for app/services/zip_streaming.py — R2-backed, concurrent
per-photo fetch into a streamed ZIP archive.

These exercise `_resolve_for_zip` and `generate_zip_stream` directly (mocking
`app.services.zip_streaming.r2.*`), rather than through the HTTP endpoints —
endpoint-level coverage (cross-event rejection, 200-photo cap, single
download_events row per ZIP) lives in tests/test_photo_actions.py, and
mixed-format archive content lives in tests/test_gallery.py.
"""
import io
import uuid
import zipfile
from unittest.mock import patch

from app.services import r2
from app.services.zip_streaming import Photo, _resolve_for_zip, generate_zip_stream


def _real_jpeg_bytes(size=(20, 10), color=(200, 100, 50)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, "JPEG")
    return buf.getvalue()


def _real_png_bytes(size=(20, 10), color=(10, 200, 50)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, "PNG")
    return buf.getvalue()


def _real_heic_bytes(size=(20, 10), color=(10, 20, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="HEIF")
    return buf.getvalue()


def _make_photo(filename: str, storage_path: str | None = None) -> Photo:
    return Photo(
        id=uuid.uuid4(),
        storage_path=storage_path or f"events/e/{uuid.uuid4()}.jpg",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# _resolve_for_zip
# ---------------------------------------------------------------------------


def test_resolve_jpeg_passthrough_unconverted():
    event_id = uuid.uuid4()
    photo = _make_photo("original.jpg")
    jpeg_bytes = _real_jpeg_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=jpeg_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", return_value=jpeg_bytes) as mock_dl, \
         patch("app.services.zip_streaming.r2.head_object") as mock_head, \
         patch("app.services.zip_streaming.r2.put_object") as mock_put:
        result = _resolve_for_zip(event_id, photo)

    assert result == (photo.filename, jpeg_bytes)
    mock_dl.assert_called_once_with(photo.storage_path)
    mock_head.assert_not_called()
    mock_put.assert_not_called()


def test_resolve_png_passthrough_unconverted():
    event_id = uuid.uuid4()
    photo = _make_photo("original.png")
    png_bytes = _real_png_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=png_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", return_value=png_bytes), \
         patch("app.services.zip_streaming.r2.head_object") as mock_head:
        result = _resolve_for_zip(event_id, photo)

    assert result == (photo.filename, png_bytes)
    mock_head.assert_not_called()


def test_resolve_heic_converts_and_caches():
    event_id = uuid.uuid4()
    photo = _make_photo("IMG_1.HEIC")
    heic_bytes = _real_heic_bytes()
    expected_key = f"events/{event_id}/downloads/{photo.id}.jpg"

    with patch("app.services.zip_streaming.r2.read_range", return_value=heic_bytes[:16]), \
         patch("app.services.zip_streaming.r2.head_object", return_value=False), \
         patch("app.services.zip_streaming.r2.download_object", return_value=heic_bytes), \
         patch("app.services.zip_streaming.r2.put_object") as mock_put:
        result = _resolve_for_zip(event_id, photo)

    assert result is not None
    filename, data = result
    assert filename == "IMG_1.jpg"
    assert data[:2] == b"\xff\xd8"  # real JPEG magic bytes, not the raw HEIC
    mock_put.assert_called_once()
    put_key, put_body, put_content_type = mock_put.call_args[0]
    assert put_key == expected_key
    assert put_content_type == "image/jpeg"


def test_resolve_heic_reuses_cached_conversion_on_second_call():
    event_id = uuid.uuid4()
    photo = _make_photo("IMG_1.HEIC")
    heic_bytes = _real_heic_bytes()
    cached_jpeg_bytes = _real_jpeg_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=heic_bytes[:16]), \
         patch("app.services.zip_streaming.r2.head_object", return_value=True), \
         patch("app.services.zip_streaming.r2.download_object", return_value=cached_jpeg_bytes) as mock_dl, \
         patch("app.services.zip_streaming.r2.put_object") as mock_put:
        result = _resolve_for_zip(event_id, photo)

    assert result == ("IMG_1.jpg", cached_jpeg_bytes)
    mock_dl.assert_called_once_with(f"events/{event_id}/downloads/{photo.id}.jpg")
    mock_put.assert_not_called()


def test_resolve_returns_none_when_header_read_fails():
    event_id = uuid.uuid4()
    photo = _make_photo("missing.jpg")

    with patch(
        "app.services.zip_streaming.r2.read_range",
        side_effect=r2.StorageUnavailableError("boom"),
    ):
        result = _resolve_for_zip(event_id, photo)

    assert result is None


def test_resolve_falls_back_to_original_on_conversion_failure():
    """If HEIC->JPEG conversion raises, fall back to the (already-fetched)
    original bytes/filename rather than skipping the photo."""
    event_id = uuid.uuid4()
    photo = _make_photo("IMG_2.HEIC")
    not_really_an_image = b"not-a-real-image-payload"

    with patch("app.services.zip_streaming.r2.read_range", return_value=not_really_an_image[:16]), \
         patch("app.services.zip_streaming.r2.head_object", return_value=False), \
         patch("app.services.zip_streaming.r2.download_object", return_value=not_really_an_image), \
         patch("app.services.zip_streaming.r2.put_object") as mock_put:
        result = _resolve_for_zip(event_id, photo)

    assert result == (photo.filename, not_really_an_image)
    mock_put.assert_not_called()


def test_resolve_returns_none_when_conversion_fails_and_original_never_fetched():
    """If head_object itself blows up (StorageUnavailableError), there is no
    already-fetched original to fall back to — the photo is skipped."""
    event_id = uuid.uuid4()
    photo = _make_photo("IMG_3.HEIC")
    heic_bytes = _real_heic_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=heic_bytes[:16]), \
         patch(
             "app.services.zip_streaming.r2.head_object",
             side_effect=r2.StorageUnavailableError("boom"),
         ), \
         patch("app.services.zip_streaming.r2.download_object") as mock_dl:
        result = _resolve_for_zip(event_id, photo)

    assert result is None
    mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# generate_zip_stream
# ---------------------------------------------------------------------------


def _drain(chunks_iter) -> bytes:
    return b"".join(chunks_iter)


def test_generate_zip_stream_includes_all_resolved_photos():
    event_id = uuid.uuid4()
    photos = [_make_photo(f"p{i}.jpg") for i in range(5)]
    jpeg_bytes = _real_jpeg_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=jpeg_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", return_value=jpeg_bytes):
        content = _drain(generate_zip_stream(photos, event_id))

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
        assert names == [f"p{i}.jpg" for i in range(5)]
        for name in names:
            assert zf.read(name) == jpeg_bytes


def test_generate_zip_stream_yields_multiple_chunks_without_full_buffering():
    """Chunks are yielded incrementally as each photo is written, rather
    than the whole archive being built in memory before anything is
    yielded."""
    event_id = uuid.uuid4()
    # Large-ish photos so zipfile flushes more than once across several
    # writes, and enough of them that a single upfront buffer would be an
    # obviously different (much larger) code path.
    photos = [_make_photo(f"p{i}.jpg") for i in range(20)]
    jpeg_bytes = _real_jpeg_bytes(size=(300, 200))

    with patch("app.services.zip_streaming.r2.read_range", return_value=jpeg_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", return_value=jpeg_bytes):
        chunks = list(generate_zip_stream(photos, event_id))

    assert len(chunks) > 1
    content = b"".join(chunks)
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert len(zf.namelist()) == 20


def test_generate_zip_stream_skips_unresolvable_photos():
    event_id = uuid.uuid4()
    good_photo = _make_photo("good.jpg")
    bad_photo = _make_photo("bad.jpg")
    jpeg_bytes = _real_jpeg_bytes()

    def fake_read_range(key, start, end):
        if key == bad_photo.storage_path:
            raise r2.StorageUnavailableError("missing")
        return jpeg_bytes[:16]

    with patch("app.services.zip_streaming.r2.read_range", side_effect=fake_read_range), \
         patch("app.services.zip_streaming.r2.download_object", return_value=jpeg_bytes):
        content = _drain(generate_zip_stream([good_photo, bad_photo], event_id))

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
        assert names == ["good.jpg"]


def test_generate_zip_stream_numbers_duplicate_filenames():
    event_id = uuid.uuid4()
    photos = [_make_photo("same.jpg") for _ in range(3)]
    jpeg_bytes = _real_jpeg_bytes()

    with patch("app.services.zip_streaming.r2.read_range", return_value=jpeg_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", return_value=jpeg_bytes):
        content = _drain(generate_zip_stream(photos, event_id))

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
        # Matches the pre-existing (unchanged) numbering scheme byte-for-byte:
        # the first occurrence is unnumbered, subsequent ones start at (2).
        assert names == ["same.jpg", "same (2).jpg", "same (3).jpg"]


def test_generate_zip_stream_preserves_input_order_despite_concurrency():
    """ThreadPoolExecutor.map() yields results in input order even though
    resolution happens concurrently — slow the first photo down relative to
    the others to prove ordering isn't just an artifact of fetch speed."""
    import time

    event_id = uuid.uuid4()
    photos = [_make_photo(f"p{i}.jpg") for i in range(4)]
    jpeg_bytes = _real_jpeg_bytes()

    def fake_download_object(key):
        if key == photos[0].storage_path:
            time.sleep(0.05)
        return jpeg_bytes

    with patch("app.services.zip_streaming.r2.read_range", return_value=jpeg_bytes[:16]), \
         patch("app.services.zip_streaming.r2.download_object", side_effect=fake_download_object):
        content = _drain(generate_zip_stream(photos, event_id))

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert zf.namelist() == [f"p{i}.jpg" for i in range(4)]
