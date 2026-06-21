# ADR: Photo-Album Denormalization — Keep `album_id` Alongside `photo_albums`

**Date:** 2026-06-21
**Status:** Accepted
**Deciders:** Engineering

---

## Context

The original `photos` table has a single `album_id` FK column (single-album assignment, used in guest gallery filtering). The Photographer Dashboard design calls for many-to-many photo–album assignment via a new `photo_albums` join table.

The guest gallery service (`services/gallery.py`) filters photos by album using:

```sql
WHERE photos.album_id = :album_id
```

This query hits indexed columns (`ix_photos_gallery_alb_latest`, `ix_photos_gallery_alb_popular`, `ix_photos_gallery_alb_choice`) set up in migration `004`. Changing to a join-table query for the guest gallery would require rewriting the gallery service and re-indexing — out of scope for this epic.

---

## Decision

Keep `photos.album_id` (denormalized "primary album") in parallel with the new `photo_albums` many-to-many join table. Both write paths must keep the two in sync:

- `PUT /photos/{photo_id}/albums` — sets `photo_albums` rows **and** sets `photo.album_id = album_ids[0]` (or `NULL` if empty).
- `PATCH /photos/{photo_id}/album` — sets `photo.album_id` **and** replaces the `photo_albums` rows for this photo.
- `POST /photos` (simple upload) — sets `photo.album_id` and optionally inserts one `photo_albums` row if an album is provided.

The `album_id` column therefore always reflects the "primary" album (first in the ordered list), or `NULL` if unassigned.

---

## Options Considered

### Option A — Remove `album_id`, use only `photo_albums` (join-table query everywhere)
- Pros: clean data model, no denormalization drift.
- Cons: requires rewriting the guest gallery service and all gallery indexes within this epic, which is out of scope and carries regression risk for the guest flow.

### Option B — Keep `album_id` as denormalized primary album (chosen)
- Pros: guest gallery query and indexes unchanged; low-risk change; consistent with existing code.
- Cons: two write paths must be kept in sync; future Album & Gallery Browsing epic must update gallery filtering and can then drop `album_id`.

---

## Consequences

**Positive:**
- Zero changes to the guest gallery critical path — no regression risk.
- Gallery queries remain O(1) via existing composite indexes.

**Negative / Risks:**
- Any direct DB write (bypassing the API) that touches only one of the two structures will introduce drift. Callers **must** use the API.
- The denormalized `album_id` always represents the first assigned album; if a photo's assignments are reordered via the API the primary album will change accordingly.

**Future action:**
The Album & Gallery Browsing epic should migrate gallery filtering to use `photo_albums` and, once verified, drop the `album_id` column with a new migration.

---

## References

- Migration: `alembic/versions/006_photographer_dashboard.py`
- Write paths: `routers/photos.py` — `upload_photo`, `update_photo_album`, `set_photo_albums`
- Gallery service: `services/gallery.py`
- Indexes: `alembic/versions/004_album_gallery.py`
