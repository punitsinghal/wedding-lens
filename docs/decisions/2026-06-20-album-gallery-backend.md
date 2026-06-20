# ADR: Album Gallery Backend — Pagination, Thumbnail Generation, and Sort Strategy

**Date:** 2026-06-20
**Status:** Accepted (2026-06-20)
**Deciders:** Engineering

---

## Context

The album gallery requires a paginated photo browsing API that supports three sort orders (latest, popular, photographer-choice), album tab filtering, per-photo thumbnail serving, and a download counter. Several design choices needed to be made consistently.

---

## Decision

### 1. Thumbnails generated in the face pipeline, not on request

Thumbnails are generated as a side-effect of the face processing pipeline (`_run_pipeline`), not on-demand at serve time. This avoids per-request PIL overhead and keeps the serving layer simple (FileResponse). A `thumbnail_path` column on `photos` tracks availability; `NULL` means not yet generated or failed.

Thumbnail generation failure is non-fatal: the pipeline logs a warning and continues. Face processing is the critical path; a missing thumbnail degrades UX but does not break the pipeline.

### 2. Thumbnail format: 600px-wide WebP at 85 quality

WebP at 600px provides a good balance of visual quality and file size for gallery grid display. 600px covers common 2-column and 3-column grid layouts on mobile and desktop. `quality=85` is a widely used default that eliminates most visible artefacts.

### 3. Pagination is always server-side; max limit=50

All gallery list endpoints enforce server-side pagination with a hard cap of 50 items per page. This prevents unbounded queries against events with thousands of photos and keeps latency predictable.

### 4. Sort-order composite indexes on photos

Six composite indexes are added to `photos` to make the three sort orders efficient both for all-photos and per-album queries. The indexes are declared on the ORM model and created via migration 004. The ORM `__table_args__` uses column names (no DESC) for SQLite compatibility in tests; the migration uses `sa.text("col DESC")` for PostgreSQL to match the query access patterns.

### 5. Photographer-choice PATCH requires owner JWT, not guest token

The `PATCH /photos/{id}/photographer-choice` endpoint uses `get_current_user` (owner bearer JWT), not `get_validated_guest_event`. This ensures guests cannot flag photos. A guest token submitted to this endpoint returns 401 (bearer scheme rejects it as not a valid owner JWT) rather than 403, which is acceptable — the security property (guests cannot toggle the flag) is enforced.

### 6. download_count incremented atomically in the download endpoint

`UPDATE photos SET download_count = download_count + 1 WHERE id = ? AND event_id = ?` is issued atomically before streaming the file. This is safe under concurrent requests and does not require a separate transaction or optimistic locking.

---

## Options Considered

- **On-demand thumbnail generation:** Simpler deployment, but adds PIL CPU overhead to every thumbnail request. Rejected to keep serving latency predictable.
- **Thumbnail stored in Qdrant payload:** Not appropriate — Qdrant is for vectors. File metadata belongs in PostgreSQL.
- **Separate thumbnail service:** Over-engineered for a single-VM deployment.

---

## Consequences

- Photos uploaded before migration 004 will have `thumbnail_path = NULL` until they are reprocessed.
- The face pipeline now imports Pillow (`PIL`). Pillow must be present in the venv.
- Gallery endpoints follow the same guest-token refresh pattern as other guest endpoints: `X-Guest-Token` header is set on every response.

---

## References

- `backend/app/routers/gallery.py`
- `backend/app/services/gallery.py`
- `backend/app/services/face_pipeline.py` — `_generate_thumbnail`
- `backend/alembic/versions/004_album_gallery.py`
