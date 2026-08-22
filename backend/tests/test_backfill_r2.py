"""Tests for the R2 backfill script's core logic (scripts/backfill_r2.py).

These exercise the key computation, upload/skip decision logic, --dry-run
short-circuiting, and the verification-pass logic against a small fake local
file tree (tmp_path) with r2.get_object_size / r2.put_object / r2.head_object
mocked — no real R2 or Postgres infrastructure involved.
"""
import uuid
from unittest.mock import patch

import pytest

from app.models.photo import Photo
from app.services import r2
from scripts import backfill_r2


# ---------------------------------------------------------------------------
# key_for_path
# ---------------------------------------------------------------------------


def test_key_for_path_computes_posix_relative_key(tmp_path):
    storage_root = tmp_path
    file_path = storage_root / "events" / "e1" / "thumbs" / "p1.webp"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"data")

    key = backfill_r2.key_for_path(file_path, storage_root)

    assert key == "events/e1/thumbs/p1.webp"


# ---------------------------------------------------------------------------
# iter_local_files
# ---------------------------------------------------------------------------


def test_iter_local_files_walks_nested_tree(tmp_path):
    events_root = tmp_path / "events"
    (events_root / "e1").mkdir(parents=True)
    (events_root / "e1" / "photo.jpg").write_bytes(b"a")
    (events_root / "e1" / "thumbs").mkdir()
    (events_root / "e1" / "thumbs" / "photo.webp").write_bytes(b"b")

    found = {p.name for p in backfill_r2.iter_local_files(events_root)}

    assert found == {"photo.jpg", "photo.webp"}


def test_iter_local_files_missing_root_yields_nothing(tmp_path):
    missing_root = tmp_path / "does-not-exist"

    assert list(backfill_r2.iter_local_files(missing_root)) == []


# ---------------------------------------------------------------------------
# upload_file — skip / reupload / upload decision logic
# ---------------------------------------------------------------------------


def test_upload_file_skips_when_size_matches(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=5) as mock_size, \
         patch.object(r2, "put_object") as mock_put:
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert result == "skipped"
    mock_size.assert_called_once_with("events/e1/photo.jpg")
    mock_put.assert_not_called()


def test_upload_file_reuploads_when_size_mismatched(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=3), \
         patch.object(r2, "put_object") as mock_put:
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert result == "uploaded"
    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args[0][0] == "events/e1/photo.jpg"
    assert call_args[0][1] == b"12345"


def test_upload_file_uploads_when_missing(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object") as mock_put:
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert result == "uploaded"
    mock_put.assert_called_once()


def test_upload_file_guesses_content_type(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object") as mock_put:
        backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert mock_put.call_args[0][2] == "image/jpeg"


def test_upload_file_falls_back_to_octet_stream_for_unknown_type(tmp_path):
    path = tmp_path / "photo.unknownext"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object") as mock_put:
        backfill_r2.upload_file("events/e1/photo.unknownext", path, dry_run=False)

    assert mock_put.call_args[0][2] == "application/octet-stream"


def test_upload_file_catches_storage_unavailable_and_returns_failed(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", side_effect=r2.StorageUnavailableError("boom")):
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert result == "failed"


def test_upload_file_put_failure_returns_failed(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object", side_effect=r2.StorageUnavailableError("boom")):
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=False)

    assert result == "failed"


# ---------------------------------------------------------------------------
# --dry-run behavior
# ---------------------------------------------------------------------------


def test_upload_file_dry_run_never_calls_put_object(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object") as mock_put:
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=True)

    assert result == "uploaded"
    mock_put.assert_not_called()


def test_upload_file_dry_run_skip_still_skips(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"12345")

    with patch.object(r2, "get_object_size", return_value=5), \
         patch.object(r2, "put_object") as mock_put:
        result = backfill_r2.upload_file("events/e1/photo.jpg", path, dry_run=True)

    assert result == "skipped"
    mock_put.assert_not_called()


def test_run_upload_pass_dry_run_never_calls_put_object(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)
    (events_root / "photo1.jpg").write_bytes(b"aaa")
    (events_root / "photo2.jpg").write_bytes(b"bb")

    with patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object") as mock_put:
        stats = backfill_r2.run_upload_pass(tmp_path, dry_run=True)

    assert stats.scanned == 2
    assert stats.uploaded == 2
    assert stats.failed == 0
    mock_put.assert_not_called()


def test_run_upload_pass_mixed_outcomes(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)
    (events_root / "already-present.jpg").write_bytes(b"aaaa")
    (events_root / "mismatched.jpg").write_bytes(b"bbbb")
    (events_root / "missing.jpg").write_bytes(b"cccc")

    def fake_get_object_size(key):
        if "already-present" in key:
            return 4  # matches local size
        if "mismatched" in key:
            return 1  # does not match local size
        return None  # missing entirely

    with patch.object(r2, "get_object_size", side_effect=fake_get_object_size), \
         patch.object(r2, "put_object") as mock_put:
        stats = backfill_r2.run_upload_pass(tmp_path, dry_run=False)

    assert stats.scanned == 3
    assert stats.skipped == 1
    assert stats.uploaded == 2
    assert stats.failed == 0
    assert mock_put.call_count == 2


def test_run_upload_pass_tracks_failures_and_continues(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)
    (events_root / "good.jpg").write_bytes(b"aaaa")
    (events_root / "bad.jpg").write_bytes(b"bbbb")

    def fake_get_object_size(key):
        if "bad" in key:
            raise r2.StorageUnavailableError("boom")
        return None

    with patch.object(r2, "get_object_size", side_effect=fake_get_object_size), \
         patch.object(r2, "put_object"):
        stats = backfill_r2.run_upload_pass(tmp_path, dry_run=False)

    assert stats.scanned == 2
    assert stats.uploaded == 1
    assert stats.failed == 1
    assert "events/e1/bad.jpg" in stats.failed_keys


# ---------------------------------------------------------------------------
# verify_keys / verification-pass logic
# ---------------------------------------------------------------------------


def test_verify_keys_identifies_missing_keys():
    keys = ["events/e1/a.jpg", "events/e1/b.jpg", "events/e1/c.jpg"]

    def fake_head_object(key):
        return key != "events/e1/b.jpg"

    with patch.object(r2, "head_object", side_effect=fake_head_object):
        stats = backfill_r2.verify_keys(keys)

    assert stats.checked == 3
    assert stats.missing == ["events/e1/b.jpg"]


def test_verify_keys_all_present():
    keys = ["events/e1/a.jpg", "events/e1/b.jpg"]

    with patch.object(r2, "head_object", return_value=True):
        stats = backfill_r2.verify_keys(keys)

    assert stats.checked == 2
    assert stats.missing == []


def test_verify_keys_treats_storage_error_as_missing():
    keys = ["events/e1/a.jpg"]

    with patch.object(r2, "head_object", side_effect=r2.StorageUnavailableError("boom")):
        stats = backfill_r2.verify_keys(keys)

    assert stats.missing == ["events/e1/a.jpg"]


# ---------------------------------------------------------------------------
# collect_db_keys
# ---------------------------------------------------------------------------


def _photo(storage_path, thumbnail_path=None) -> Photo:
    return Photo(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        filename="f.jpg",
        storage_path=storage_path,
        file_size=100,
        thumbnail_path=thumbnail_path,
    )


def test_collect_db_keys_includes_storage_and_thumbnail_paths():
    photos = [
        _photo("events/e1/a.jpg", "events/e1/thumbs/a.webp"),
        _photo("events/e1/b.jpg", None),
    ]

    keys = backfill_r2.collect_db_keys(photos)

    assert keys == [
        "events/e1/a.jpg",
        "events/e1/thumbs/a.webp",
        "events/e1/b.jpg",
    ]


def test_collect_db_keys_empty_list():
    assert backfill_r2.collect_db_keys([]) == []


# ---------------------------------------------------------------------------
# run_verification_pass — integration of fetch + collect + verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_verification_pass_reports_missing_db_keys():
    photos = [
        _photo("events/e1/a.jpg", "events/e1/thumbs/a.webp"),
        _photo("events/e1/b.jpg", None),
    ]

    def fake_head_object(key):
        return key != "events/e1/thumbs/a.webp"

    with patch.object(backfill_r2, "fetch_all_photos", return_value=photos), \
         patch.object(r2, "head_object", side_effect=fake_head_object):
        stats = await backfill_r2.run_verification_pass()

    assert stats.checked == 3
    assert stats.missing == ["events/e1/thumbs/a.webp"]


# ---------------------------------------------------------------------------
# main() exit code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_returns_zero_when_no_failures_or_missing(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)
    (events_root / "photo.jpg").write_bytes(b"aaaa")

    with patch.object(backfill_r2.settings, "STORAGE_PATH", str(tmp_path)), \
         patch.object(r2, "get_object_size", return_value=None), \
         patch.object(r2, "put_object"), \
         patch.object(backfill_r2, "fetch_all_photos", return_value=[]):
        exit_code = await backfill_r2.main(dry_run=False)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_main_returns_nonzero_when_upload_failed(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)
    (events_root / "photo.jpg").write_bytes(b"aaaa")

    with patch.object(backfill_r2.settings, "STORAGE_PATH", str(tmp_path)), \
         patch.object(r2, "get_object_size", side_effect=r2.StorageUnavailableError("boom")), \
         patch.object(backfill_r2, "fetch_all_photos", return_value=[]):
        exit_code = await backfill_r2.main(dry_run=False)

    assert exit_code == 1


@pytest.mark.asyncio
async def test_main_returns_nonzero_when_verification_missing(tmp_path):
    events_root = tmp_path / "events" / "e1"
    events_root.mkdir(parents=True)

    photos = [_photo("events/e1/missing.jpg")]

    with patch.object(backfill_r2.settings, "STORAGE_PATH", str(tmp_path)), \
         patch.object(backfill_r2, "fetch_all_photos", return_value=photos), \
         patch.object(r2, "head_object", return_value=False):
        exit_code = await backfill_r2.main(dry_run=False)

    assert exit_code == 1
