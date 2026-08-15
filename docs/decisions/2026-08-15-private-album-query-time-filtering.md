# ADR: Private Album Visibility Enforced by Query-Time Filtering at Every Guest-Facing Read Path

**Date:** 2026-08-15
**Status:** Accepted
**Deciders:** Engineering

---

## Context

EPIC requirement 6 (`docs/epics/privacy-security/EPIC.md`) requires that private albums be
accessible only to authenticated guests of an event — in practice, the in-flight implementation
treats "private" as **hidden from guests entirely**, visible only to the owning photographer/event
owner, per the `test_photographer_sees_private_album_in_crud` test in
`backend/tests/test_privacy_security.py`.

A `visibility` enum (`public` | `private`, default `public`) was added to `Album`
(migration `008_album_visibility`). The guest gallery endpoints
(`GET /gallery`, `GET /gallery/albums` — `backend/app/services/gallery.py`) filter photos and
ceremony-category tabs to exclude private albums via an outer join on `Album.visibility`.

Qdrant has no concept of album visibility — face embeddings are indexed with only
`event_id` scoping (`docs/decisions/2026-06-19-face-embedding-dual-storage.md`). The guest
face-search path (`backend/app/services/face_search.py`) queries Qdrant directly by `event_id`
and, before this ADR, fetched matching `Photo` rows from PostgreSQL by `photo_id` + `event_id`
only — with no visibility check. That meant a guest whose selfie matched a photo filed in a
private album would get that photo's id and thumbnail URL back from `/search`, even though the
same photo is absent from `/gallery` and `/gallery/albums`. The gallery-level filter alone does not
protect a "hidden" album — search is a second, independent disclosure path into the same photo
table.

Guest-facing photo retrieval routes (`/photos/{photo_id}/thumbnail`, `/photos/{photo_id}/download`)
intentionally do **not** re-check visibility on every request — they require a valid guest session
token (`get_validated_guest_event`) plus a `photo_id` the guest can only have learned from an
already-filtered listing or search response. The gap was specifically that search was *handing
out* those `photo_id`s for private-album photos in the first place, which would have made the
downstream lack of a re-check exploitable.

---

## Decision

**Every guest-facing read path that can return a `photo_id` to a guest must exclude photos whose
`album_id` resolves to a private album**, filtered at query time via an outer join:

```python
.outerjoin(Album, Photo.album_id == Album.id)
.where(or_(Photo.album_id.is_(None), Album.visibility == "public"))
```

This is now applied in three places:
- `gallery_service.list_photos` (gallery photo listing)
- `gallery_service.list_album_tabs` (ceremony-category tab counts)
- `face_search.run_search` (selfie search results, after the Qdrant hit list is resolved to
  `Photo` rows)

Routes that only ever operate on a `photo_id` a guest already legitimately holds
(thumbnail/download) remain unfiltered — visibility is enforced at the point a `photo_id` is
*disclosed*, not at every point it is later dereferenced.

---

## Options Considered

| Option | Where enforced | New infra | Correctly closes the search gap |
|--------|-----------------|-----------|----------------------------------|
| **Query-time join filter at every disclosure path (selected)** | App layer, per query | None | Yes |
| Embed `visibility` into the Qdrant payload, filter there | Qdrant | Payload schema change + reindex on every toggle | Yes, but couples a Postgres-owned attribute into Qdrant, and every visibility toggle would need a payload sync job |
| Filter only at the gallery layer (status quo before this ADR) | App layer, gallery only | None | No — search still leaks private-album photos |

---

## Consequences

**Positive:**
- Closes a real disclosure gap: a guest can no longer learn a private-album photo's id via
  selfie search.
- No new infrastructure or Qdrant payload changes; `visibility` stays a Postgres-owned attribute,
  consistent with the dual-storage ADR (Postgres is authoritative metadata, Qdrant is
  vector-search-only).
- Toggling an album's visibility takes effect immediately for every guest-facing path, with no
  reindex step.

**Negative:**
- The visibility check must be remembered and re-applied at every *new* guest-facing query that
  can surface a `photo_id` — it is not centralized in one place (e.g., a single repository method).
  Any future guest-facing photo listing/search path must include the same outer-join filter.

**Convention for future code:**
- A new guest-facing endpoint that returns `photo_id`s (or anything derived from them, like
  thumbnail URLs) must filter out private-album photos at the query itself. Do not rely on the
  gallery filter alone — search demonstrated that assumption is wrong.

---

## References
- `docs/epics/privacy-security/EPIC.md` — requirement 6, private album access control
- `backend/app/services/gallery.py` — `list_photos`, `list_album_tabs`
- `backend/app/services/face_search.py` — `run_search`
- `backend/tests/test_privacy_security.py` — REQ-6 test section
- `docs/decisions/2026-06-19-face-embedding-dual-storage.md` — Qdrant holds vectors only, Postgres is authoritative
