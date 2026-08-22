#!/usr/bin/env python
"""One-off operational script: backfill photo files from the Railway Volume to R2.

Run manually by an operator during the scheduled maintenance window described
in docs/features/photo-storage-migration/design.md ("Backfill migration") and
docs/features/photo-storage-migration/requirements.md (REQ-17/18/19, Scenario 8).

This is NOT part of the running FastAPI app — it is a standalone script an
operator invokes once (and can safely re-run) before final cutover to R2.

What it does:
  1. Upload pass — walks `STORAGE_PATH/events/` on the local disk (still the
     Railway Volume at the time this runs) and, for every file found, uploads
     it to R2 under the identical relative key (`events/{event_id}/...`).
     Object keys are unchanged by this migration, so this is a pure copy, not
     a re-key. Idempotent/resumable: a file already present in R2 with a
     matching size is skipped; a missing or size-mismatched file is
     (re-)uploaded.
  2. Verification pass — queries every `Photo.storage_path` and
     `Photo.thumbnail_path` in PostgreSQL (across all events) and confirms
     each one resolves in R2 via `head_object`. This is deliberately a
     separate pass from the upload pass: its job is to catch DB/filesystem
     drift (a DB row pointing at a file that was never actually on disk, or
     that failed to upload) that a pure filesystem walk would not surface.

This script never deletes anything from the local volume — decommissioning
the Railway Volume is a separate, later, manual decision by the operator.

Usage:
    python -m scripts.backfill_r2 [--dry-run]
"""
import argparse
import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.photo import Photo
from app.services import r2

logger = logging.getLogger("weddinglens.backfill_r2")

PROGRESS_EVERY = 100


@dataclass
class UploadStats:
    scanned: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_keys: list[str] = field(default_factory=list)


@dataclass
class VerificationStats:
    checked: int = 0
    missing: list[str] = field(default_factory=list)


def key_for_path(path: Path, storage_root: Path) -> str:
    """Compute the R2 object key for a local file, relative to STORAGE_PATH.

    Posix-style forward slashes, matching the existing key convention — e.g.
    `{STORAGE_PATH}/events/{event_id}/thumbs/{photo_id}.webp` becomes
    `events/{event_id}/thumbs/{photo_id}.webp`.
    """
    return path.relative_to(storage_root).as_posix()


def iter_local_files(events_root: Path):
    """Yield every regular file under `events_root`, deterministically ordered."""
    if not events_root.is_dir():
        return
    for path in sorted(events_root.rglob("*")):
        if path.is_file():
            yield path


def upload_file(key: str, path: Path, *, dry_run: bool) -> str:
    """Upload a single local file to R2 if missing or size-mismatched.

    Returns one of "uploaded", "skipped", or "failed". Never raises —
    `r2.StorageUnavailableError` is caught and translated to "failed" so a
    single bad file does not abort the whole run.
    """
    local_size = path.stat().st_size
    try:
        r2_size = r2.get_object_size(key)
    except r2.StorageUnavailableError as exc:
        logger.error('{"event": "backfill_head_failed", "key": "%s", "error": "%s"}', key, exc)
        return "failed"

    if r2_size == local_size:
        return "skipped"

    if dry_run:
        return "uploaded"

    try:
        body = path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(path))
        r2.put_object(key, body, content_type or "application/octet-stream")
    except r2.StorageUnavailableError as exc:
        logger.error('{"event": "backfill_upload_failed", "key": "%s", "error": "%s"}', key, exc)
        return "failed"
    return "uploaded"


def run_upload_pass(storage_root: Path, *, dry_run: bool) -> UploadStats:
    """Walk STORAGE_PATH/events/ and copy every file forward to R2."""
    stats = UploadStats()
    events_root = storage_root / "events"

    for path in iter_local_files(events_root):
        key = key_for_path(path, storage_root)
        stats.scanned += 1

        result = upload_file(key, path, dry_run=dry_run)
        if result == "uploaded":
            stats.uploaded += 1
        elif result == "skipped":
            stats.skipped += 1
        else:
            stats.failed += 1
            stats.failed_keys.append(key)

        if stats.scanned % PROGRESS_EVERY == 0:
            print(
                f"[upload] scanned={stats.scanned} uploaded={stats.uploaded} "
                f"skipped={stats.skipped} failed={stats.failed}"
            )

    return stats


def verify_keys(keys: list[str]) -> VerificationStats:
    """Confirm every key in `keys` resolves in R2 via head_object.

    Read-only by nature — used for the DB-referenced-path verification pass
    (REQ-19) as well as for --dry-run, where it's the only real R2 check
    performed.
    """
    stats = VerificationStats()
    for key in keys:
        stats.checked += 1
        try:
            exists = r2.head_object(key)
        except r2.StorageUnavailableError as exc:
            logger.error('{"event": "backfill_verify_failed", "key": "%s", "error": "%s"}', key, exc)
            exists = False
        if not exists:
            stats.missing.append(key)
    return stats


def collect_db_keys(photos: list[Photo]) -> list[str]:
    """Extract every non-null storage_path/thumbnail_path from a list of Photo rows."""
    keys: list[str] = []
    for photo in photos:
        if photo.storage_path:
            keys.append(photo.storage_path)
        if photo.thumbnail_path:
            keys.append(photo.thumbnail_path)
    return keys


async def fetch_all_photos() -> list[Photo]:
    """Query every Photo row across all events — this is a one-time global migration."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Photo))
        return list(result.scalars().all())


async def run_verification_pass() -> VerificationStats:
    photos = await fetch_all_photos()
    keys = collect_db_keys(photos)
    return verify_keys(keys)


def print_summary(upload_stats: UploadStats, verify_stats: VerificationStats) -> None:
    print("\n=== Backfill summary ===")
    print(
        f"Upload pass:       scanned={upload_stats.scanned} "
        f"uploaded={upload_stats.uploaded} skipped={upload_stats.skipped} "
        f"failed={upload_stats.failed}"
    )
    if upload_stats.failed_keys:
        print("Failed upload keys:")
        for key in upload_stats.failed_keys:
            print(f"  - {key}")

    print(
        f"Verification pass: checked={verify_stats.checked} "
        f"missing={len(verify_stats.missing)}"
    )
    if verify_stats.missing:
        print("DB-referenced keys NOT found in R2 (do NOT decommission the volume yet):")
        for key in verify_stats.missing:
            print(f"  - {key}")


async def main(dry_run: bool) -> int:
    storage_root = Path(settings.STORAGE_PATH)

    print(f"Starting backfill from {storage_root} to R2 bucket '{settings.R2_BUCKET_NAME}'")
    print(f"dry_run={dry_run}")

    upload_stats = run_upload_pass(storage_root, dry_run=dry_run)
    verify_stats = await run_verification_pass()

    print_summary(upload_stats, verify_stats)

    if upload_stats.failed or verify_stats.missing:
        return 1
    return 0


if __name__ == "__main__":
    import asyncio
    import sys

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Backfill photo files from the Railway Volume to Cloudflare R2."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be uploaded/skipped without writing to R2.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(main(dry_run=args.dry_run))
    sys.exit(exit_code)
