# ADR: HEIC-to-JPEG conversion safety net for guest downloads
Date: 2026-08-21
Status: accepted

## Context

Guests were receiving `.heic`/`.heif` files when downloading photos (both
single-photo download and ZIP download). Android phones and many browsers
cannot open HEIC properly, so affected guests were left with a file they
couldn't view — a hard blocker for the core "find and download your
photos" flow this product exists for.

Two distinct gaps caused this:

1. **Upload-time validation gap (root cause).** The photographer bulk
   upload path (`app/routers/uploads.py`) already validates both a filename
   extension allowlist *and* the assembled file's magic bytes
   (`JPEG_MAGIC`/`PNG_MAGIC`) before accepting it — a real HEIC file cannot
   get through. The single-photo upload (`app/routers/photos.py`) and guest
   upload (`app/routers/guest_uploads.py`) endpoints, however, validated
   *only* the client-supplied `Content-Type` header. A client that mislabels
   a HEIC file's `Content-Type` — or a HEIC file that's been through a
   third-party "converter" app that just renames the extension without
   re-encoding — slips straight into storage undetected. This is how real
   HEIC bytes were ending up in `photo.storage_path` despite a content-type
   check nominally existing.
2. **No conversion capability anywhere.** Even setting aside the upload
   gap, nothing in the codebase could decode or convert HEIC — stock
   `Pillow` cannot open HEIC without a plugin, and prebuilt
   `opencv-python-headless` has no `libheif` support. Thumbnail/preview
   generation already silently failed for any HEIC that got through
   (caught by a broad try/except), and face detection hard-failed
   (`cv2.imdecode` returns `None`).

Fixing only (1) closes the ingestion gap going forward but doesn't help
guests if *anything* ever slips through anyway (a bug elsewhere, a future
upload path, or files ingested before this fix shipped) — and there was no
way to verify with certainty that no HEIC has already reached storage.
Fixing only (2) treats the symptom without stopping new bad files from
being written in the first place, and would mean every download pays a
conversion check even though it's rare in practice. Both were done.

## Decision

### Part 1 — magic-byte sniffing as the authoritative upload gate

Added `app/services/image_format.py` with `sniff_image_format(data: bytes)`
and `is_allowed_upload_format(data: bytes)`, factoring out the magic-byte
constants (`JPEG_MAGIC = b"\xff\xd8"`, `PNG_MAGIC = b"\x89PNG"`) that
`app/routers/uploads.py` already had, so all three upload paths
(`photos.py`, `guest_uploads.py`, `uploads.py`) share one implementation
instead of three copies of the same two constants.

- `app/routers/photos.py::upload_photo` and
  `app/routers/guest_uploads.py::upload_guest_photo` now call
  `is_allowed_upload_format(contents)` after reading the file body, in
  addition to (not instead of) the existing `Content-Type` header check.
  The header check stays as a cheap first-pass/defense-in-depth filter; the
  magic-byte check is the one that actually decides accept/reject. Both
  reject with the pre-existing `422` + `"Only JPEG and PNG files are
  accepted"` detail, so no API contract changed.
- `app/routers/uploads.py::complete_upload` now calls the same shared
  helper on the assembled file instead of its own local `is_jpeg`/`is_png`
  checks — behavior unchanged, just de-duplicated.

### Part 2 — lazy, cached HEIC→JPEG conversion at download time

Added `app/services/gallery.py::get_downloadable_path(db, event_id,
photo_id)` (and its DB-free sync core, `_resolve_downloadable`, reused by
the ZIP path) as a safety net for anything already in storage — whether
from before this fix shipped, or from some future upload path that forgets
to call the Part 1 check:

- Sniffs the *original* file's real bytes. If it's already JPEG or PNG,
  returns `(original_path, original_filename)` unchanged — **never**
  re-encodes a file that's already in a guest-safe format. (This mirrors
  the lesson from the lightbox-preview work,
  `docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md`: gratuitous
  re-encoding degrades quality for no benefit.)
- Anything else (HEIC/HEIF, or any other format) is treated as needing
  conversion. On first request, decodes with Pillow via the `pillow-heif`
  plugin, applies `ImageOps.exif_transpose` (same orientation fix used by
  `_generate_thumbnail`/`_generate_preview`), converts to RGB, and saves as
  JPEG **quality=95** — high, because this is a format-compatibility fix,
  not a size optimization. The result is cached to a deterministic,
  DB-free path (`events/{event_id}/downloads/{photo_id}.jpg`, mirroring the
  `previews/` convention) using the same atomic temp-file-then-rename
  pattern as `_generate_preview`, so a concurrent request never observes a
  partial file. A second request for the same photo hits the cache and
  never re-converts.
- The filename sent to the guest has its extension swapped for `.jpg`
  (`IMG_4521.HEIC` → `IMG_4521.jpg`) so it isn't confusingly mismatched
  with the bytes actually received.
- On conversion failure, logs a warning
  (`"event": "download_conversion_error"`, same style as
  `preview_generation_error`) and falls back to serving the original
  file/filename as-is — a guest getting a HEIC file in a rare edge case is
  better than the download failing outright. This should be rare in
  practice once Part 1 closes the ingestion gap.
- Wired into both `app/routers/gallery.py::download_photo` (single-photo
  download) and `app/services/zip_streaming.py::generate_zip_stream` (ZIP
  download), which now takes an `event_id` parameter so it can compute the
  per-photo cache path. The ZIP's existing duplicate-filename
  disambiguation logic operates on the possibly-renamed `.jpg` filename.
  `generate_zip_stream` calls the sync core (`_resolve_downloadable`)
  directly rather than the DB-based async wrapper, since it already has
  `storage_path`/`filename` from its caller's query and doesn't need a
  second DB round-trip per photo.

### Why `pillow-heif`

Chosen over the alternatives:
- `pyheif` — unmaintained (last release predates modern Pillow/Python
  versions); a genuinely risky choice for a guest-facing compatibility
  path.
- Rebuilding `opencv-python-headless` against a `libheif`-enabled system
  library, or installing a system `libheif` package — adds OS-level package
  management to what's currently a pure-`pip` dependency set, and this
  VM is a single shared 4-core/16GB box (see root `CLAUDE.md`) where we'd
  rather not add system package surface for a narrow use case.

`pillow-heif` is actively maintained, ships prebuilt wheels (no system
`libheif` needed), and integrates via `pillow_heif.register_heif_opener()`
— a single call, made once at import time in `app/services/gallery.py`
(the only module that needs HEIC decoding), after which `PIL.Image.open`
transparently handles HEIC/HEIF bytes.

**Note on the "heavy optional dependency" convention:** `docs/decisions/2026-06-20-face-pipeline-implementation.md`
established that heavy, optional dependencies (InsightFace, OpenCV, ONNX
Runtime) must be lazily imported inside a function, specifically so the dev
venv and test suite don't require ~500MB of models just to run. `pillow-heif`
is a normal, small, prebuilt-wheel pip package with no model downloads and
no meaningful import-time cost — closer to `Pillow` itself than to
InsightFace — and it's a hard (not optional) dependency of the download
path now that HEIC conversion is part of the guaranteed download contract.
It is therefore imported and registered at module top level in
`app/services/gallery.py`, not lazily; that convention's rationale (keep
optional heavy ML dependencies out of the default test/dev path) doesn't
apply here.

Bumped `Pillow` from `10.4.0` to `12.2.0` in `requirements.txt` because
`pillow-heif==1.5.0` requires `Pillow>=11.1.0`; verified with `pip check`
that no other pinned dependency conflicts with the newer Pillow.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Only fix upload validation (Part 1) | Simplest; stops new bad files | Doesn't help anything already in storage, or any future upload path that bypasses the check; no defense in depth |
| Only add download-time conversion (Part 2) | Fixes guest-visible symptom immediately regardless of how the file got there | Leaves the ingestion gap open — new HEIC keeps entering storage indefinitely; every download pays a sniff even though the underlying bug should be rare once fixed |
| Both (chosen) | Root-causes the ingestion gap and provides a safety net for anything already stored or slipping through a future path | Two code paths to maintain instead of one; small ongoing disk cost for the download cache tier |
| `pyheif` for HEIC decoding | Smaller install | Unmaintained; risky for a guest-facing path |
| System `libheif` + rebuild OpenCV | Would also unlock HEIC in the face-detection path | Adds OS package management to a single-VM deployment for a need that's currently download-only; larger blast radius of change |
| Eagerly convert HEIC to JPEG at upload time instead of lazily at download time | One conversion instead of a cache-miss-triggered one; original format never persists | Should be unreachable after Part 1 (HEIC is now rejected at upload); would also slow the upload response for a case that should no longer occur, and provides no safety net for already-stored files |

## Consequences

- Two new cache-style conventions exist for derived image assets:
  `previews/{photo_id}.webp` (lightbox) and `downloads/{photo_id}.jpg`
  (download conversion), both DB-free and deterministic from
  `event_id`/`photo_id`. Anyone adding a third derived-image use case
  should follow the same lazy-generate-and-cache-to-disk pattern established
  first by the lightbox preview ADR.
- `app/services/zip_streaming.py::generate_zip_stream` now takes an
  `event_id` parameter — both call sites in `app/routers/photo_actions.py`
  were updated. Its DTO `Photo` class gained an `id` field for the same
  reason (needed to compute the per-photo cache path).
- `app/services/gallery.py::_resolve_downloadable` is a private,
  DB-free helper intentionally imported directly by
  `zip_streaming.py` — this is the one case in this codebase where a
  service module reaches into another service module's "private" function,
  done to avoid a second DB round-trip per photo inside a ZIP that may
  contain up to 200 photos.
- If the JPEG quality/conversion parameters change later, cached
  `downloads/*.jpg` files won't self-invalidate — same caveat already
  noted for the lightbox preview cache.
- `requirements.txt`'s `Pillow` pin moved from `10.4.0` to `12.2.0`.

## References

- `backend/app/services/image_format.py` — `sniff_image_format`,
  `is_allowed_upload_format`
- `backend/app/routers/photos.py`, `backend/app/routers/guest_uploads.py`,
  `backend/app/routers/uploads.py` — upload-time magic-byte gate
- `backend/app/services/gallery.py` — `get_downloadable_path`,
  `_resolve_downloadable`, `_convert_to_jpeg`, `_download_rel_path`,
  `_swap_ext_to_jpg`
- `backend/app/routers/gallery.py` — `download_photo`
- `backend/app/services/zip_streaming.py` — `generate_zip_stream`
- `backend/app/routers/photo_actions.py` — `bulk_zip_download`,
  `favourites_zip_download`
- `backend/tests/test_photos.py`,
  `backend/tests/test_guest_uploads.py` — spoofed-Content-Type upload
  rejection tests
- `backend/tests/test_gallery.py` — Test 13 (download conversion,
  caching, ZIP mix of formats)
- `docs/decisions/2026-08-21-lazy-generated-photo-preview-tier.md` — the
  lazy-generate-and-cache pattern this mirrors, and the prior
  quality-degradation lesson about not re-encoding originals unnecessarily
- `docs/decisions/2026-06-20-face-pipeline-implementation.md` — the
  lazy-import convention for heavy optional dependencies, and why it
  doesn't apply to `pillow-heif`
