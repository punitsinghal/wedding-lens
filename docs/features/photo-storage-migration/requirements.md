## Epic
(standalone — no parent epic; cross-cutting infrastructure change spanning Photographer Dashboard, Album & Gallery Browsing, Photo Actions, AI Face Processing, and Event Management)

## Purpose
Migrate PicsLeLo's photo file storage — originals, thumbnails, previews, and the HEIC download-conversion cache — from the single-instance Railway Volume to Cloudflare R2 object storage, so the platform can host multiple concurrent events without recurring storage-capacity failures, remove the architectural blocker on horizontal backend scaling, and eliminate Railway's per-GB egress cost on guest-facing photo reads — while preserving today's event-scoped access guarantees for photographers and guests.

## Scenarios in scope
1. Photographer uploads a new photo via chunked upload — file bytes land in R2 instead of the Railway Volume, with existing resumability/dedup behavior preserved.
2. The face-processing pipeline generates a thumbnail for a newly uploaded photo — thumbnail read/write goes to R2 instead of local disk.
3. Guest browses the gallery grid — thumbnails are served from R2-backed storage, preserving lazy-loading and event-scoped isolation.
4. Guest opens a photo in the lightbox — the on-demand preview (generate-if-missing) is generated from, and cached in, R2.
5. Guest downloads a single original photo — served from R2, preserving original filename/attachment behavior and event-scope validation.
6. Guest downloads a bulk ZIP of multiple originals (face-search results or favourites) — backend fetches the constituent objects from R2 server-side to build and stream the combined archive.
7. Guest downloads a non-JPEG/PNG (HEIC) original — the HEIC→JPEG conversion cache is generated lazily and stored in R2.
8. Photos already stored on the Railway Volume are migrated to R2 as a one-time backfill.
9. An event is permanently deleted (soft-delete grace period expiring, or admin force-delete) — the corresponding R2 objects (original, thumbnail, preview, download-cache) are removed, not orphaned.
10. R2 is unreachable or misconfigured (bad credentials, network failure, bucket missing) at upload or read time — the system surfaces a clear, actionable error rather than failing silently or corrupting state.

## User stories / use cases
- As a photographer, I want my uploads to keep working exactly as they do today, so that I don't notice or need to adapt to the storage backend change.
- As a photographer, I want face processing (and its thumbnails) to keep working transparently after upload, so that the gallery is guest-ready the same way it is today.
- As a guest, I want the gallery grid to load thumbnails quickly and only show photos from my event, so that browsing feels the same as before.
- As a guest, I want to open a photo at full resolution in the lightbox without noticing any slowdown, so that my viewing experience is unaffected by the migration.
- As a guest, I want to download my photo and get the original file with its proper name, so that downloading still works exactly as it does today.
- As a guest, I want to download a ZIP of all my photos within a reasonable time, so that a large batch download doesn't become frustratingly slow after this change.
- As a guest, I want to download a HEIC photo as a JPEG the same way I can today, so that format compatibility isn't affected by the migration.
- As a bride/groom or admin, I want my event's existing photos to still be there and working after the migration, so that I never lose access to my gallery.
- As a bride/groom, I want my deleted event's photos to actually be gone from all storage after the retention period, so that my privacy expectation is honored.
- As a photographer or guest, I want a clear error (not a broken page) if the storage backend has a problem, so that I know something is wrong rather than assuming my upload or download silently failed.

## Functional requirements

### Scenario 1 — Chunked upload → R2
1. REQ-1 (Scenario 1): Chunk writes must persist to R2-backed storage instead of the Railway Volume, preserving existing resumability (received-chunk tracking, session state) unchanged from the photographer's perspective.
2. REQ-2 (Scenario 1): The upload-complete step must assemble/produce the final original photo object in R2, preserving existing content-hash dedup behavior.
3. REQ-3 (Scenario 1): Upload reliability for large batches must not regress — the existing bar (1,000 photos without manual retry; a 500-photo event uploadable in under 30 minutes, per `photographer-dashboard` NFRs) still applies.

### Scenario 2 — Thumbnail generation → R2
4. REQ-4 (Scenario 2): The face-processing pipeline must read the original from R2 (not local disk) to run detection/embedding and thumbnail generation.
5. REQ-5 (Scenario 2): Generated thumbnails must be written to R2, addressable the same way as today (per-event, per-photo-id).
6. REQ-6 (Scenario 2): A thumbnail write failure must remain non-fatal to the overall face-processing job — existing behavior (logged, not blocking) is preserved.

### Scenario 3 — Gallery grid thumbnails from R2
7. REQ-7 (Scenario 3): Gallery grid behavior (lazy-loaded thumbnails, no original fetch on render) must be unchanged from the guest's perspective.
8. REQ-8 (Scenario 3): Thumbnail access must remain strictly event-scoped — no thumbnail for one event must be retrievable via another event's guest session.

### Scenario 4 — Lightbox/preview from R2
9. REQ-9 (Scenario 4): On-demand preview generation (first lightbox open) must read from and cache to R2, preserving current generate-once behavior.
10. REQ-10 (Scenario 3 & 4): Signed read URLs (or equivalent access mechanism) for thumbnails, previews, and lightbox images must remain valid for at least the duration of a guest's normal active browsing session — a guest must never see a broken/expired image mid-session.

### Scenario 5 — Single original download from R2
11. REQ-11 (Scenario 5): Downloads must continue to serve the original file with a `Content-Disposition: attachment` header and the original filename.
12. REQ-12 (Scenario 5): Event-scope validation (guest session `event_id` must match the requested photo's `event_id`) must occur before any access mechanism is issued, regardless of delivery method.
13. REQ-13 (Scenario 5): The download-count increment (feeds the gallery's Popular sort) must continue to fire reliably for every completed download.

### Scenario 6 — Bulk ZIP download
14. REQ-14 (Scenario 6): ZIP generation must retrieve each constituent original from R2 server-side and stream the resulting archive to the guest — existing caps and behavior are preserved: 200-photo maximum, filename conventions (`wedding-{event-slug}-my-photos.zip` / `-my-favourites.zip`), per-photo event-scope validation, and no full in-memory buffering of the archive.
15. REQ-15 (Scenario 6): ZIP generation for 100 photos must complete in under 30 seconds — the existing `photo-actions` NFR-2 bar is preserved, not relaxed, despite the storage backend change.

### Scenario 7 — HEIC download-conversion cache
16. REQ-16 (Scenario 7): HEIC→JPEG conversion must read the original from and write the cached JPEG to R2, preserving existing lazy/generate-once caching behavior.

### Scenario 8 — Backfill migration
17. REQ-17 (Scenario 8): All existing photo objects (originals, thumbnails, previews, download-cache) on the Railway Volume must be copied to R2 before an event's traffic is cut over to the new storage backend.
18. REQ-18 (Scenario 8): The backfill may run within a scheduled, short maintenance window during which photo uploads and guest reads are paused — zero-downtime dual-write is not required.
19. REQ-19 (Scenario 8): Post-backfill, every PostgreSQL-referenced photo path must be verified resolvable in R2 before the Railway Volume copy is treated as disposable.

### Scenario 9 — Deletion cleanup
20. REQ-20 (Scenario 9): When an event's 30-day soft-delete grace period expires, or an admin force-deletes an event, the purge job must delete the corresponding R2 objects for that `event_id` (originals, thumbnails, previews, download-cache) in addition to the existing PostgreSQL and Qdrant purge steps.
21. REQ-21 (Scenario 9): The existing "no partial deletion" guarantee (`event-management` NFR-3) extends to R2 — a completed purge must not leave orphaned objects in the bucket for that event.

### Scenario 10 — R2 unreachable/misconfigured
22. REQ-22 (Scenario 10): Upload endpoints must return a clear, distinguishable error when R2 is unreachable or misconfigured — not a raw 500 or generic failure.
23. REQ-23 (Scenario 10): Read paths (gallery, lightbox, single/bulk download) must surface a clear error rather than a silently broken image or a corrupted/incomplete ZIP.
24. REQ-24 (Scenario 10): A storage failure must never leave PostgreSQL in an inconsistent state — e.g., a chunk must not be marked received, or a Photo row created, unless the corresponding R2 write actually succeeded.

## Non-functional requirements
- NFR-1: The gallery list endpoint's existing performance bar (`album-gallery` NFR-1: 50-photo batch served under 500ms p95 at 50,000 photos) must not regress as a result of the storage backend change.
- NFR-2: Single-photo download must still begin within 2 seconds of request (`photo-actions` NFR-1), re-measured against R2 rather than local SSD.
- NFR-3: Bulk ZIP generation for 100 photos must complete in under 30 seconds (carried forward from `photo-actions` NFR-2 — see REQ-15).
- NFR-4: Event-scoped isolation must hold at the storage layer exactly as it does today at the API layer — no signed URL, object key, or storage credential must allow cross-event access.
- NFR-5: Upload throughput/reliability for large batches must not regress (`photographer-dashboard` NFRs — 1,000 photos without manual retry; 500-photo event in under 30 minutes).
- NFR-6: All photo objects are encrypted at rest by R2 by default — a net improvement over the current local-disk baseline, where photo files were not separately encrypted.

## Context
- Source decision: `docs/decisions/2026-08-22-cloudflare-r2-photo-storage.md` — chooses Cloudflare R2 over a larger Railway Volume or AWS S3, and chooses backend-issued presigned URLs over full backend-proxying, specifically to realize R2's zero-egress cost benefit.
- Triggering incident: the Railway `backend-volume` (500MB) reached 97.7% capacity on 2026-08-22, causing upload failures (`OSError: [Errno 28] No space left on device`) during a live event upload. Photo data alone was 392.6MB (78.5%) of the volume at the time.
- R2 credentials (account ID, access key, secret key, bucket name, endpoint) are already provisioned as Railway backend environment variables as of this grooming session.
- CORS configuration on the R2 bucket (allowed origins, methods) is an external Cloudflare-side dependency, already scoped in prior discussion — not re-derived here.
- This migration touches storage-layer assumptions documented as fact in four other feature docs, which will read as stale once this ships and should be updated in the same change: `photographer-dashboard/requirements.md` (REQ-3, Context — "stores it on the local SSD"), `photo-actions/requirements.md` (REQ-1, NFR-1/2, Architectural notes — "local SSD", `FileResponse` from disk), `album-gallery/requirements.md` (OQ-3 — thumbnail storage location, still marked open there despite being implemented), and `event-management/requirements.md` (REQ-15/28 — "photos on disk (`STORAGE_PATH`)").
- `docs/architecture/constraints.md` rule 4 ("Frontend talks only to the backend REST API — never directly to Qdrant, PostgreSQL, or storage") requires an explicit documented carve-out for backend-issued, short-lived, single-object signed URLs — decided in the ADR, to be written alongside implementation.
- Guest session tokens have a 24-hour idle expiry (`photo-actions` Context) — relevant context for sizing signed read URL validity (REQ-10) in `/design`.

## Addendum (added during /design impact analysis, 2026-08-22)
Impact analysis (`docs/wip/analysis-photo-storage-migration-r2-2026-08-22.md`) surfaced two live features not covered by the scenarios above, neither documented in any existing `docs/features/*/requirements.md`. Both follow the same storage pattern already specified for Scenarios 1/2/9 — no new user-facing behavior or acceptance criteria, just additional storage touch points folded into this migration's implementation scope:
- **Guest photo uploads** (`guest_uploads_enabled` toggle, `guest_uploads.py`, `GuestUploadModal.tsx`): a single-request (non-chunked) upload path guests can use when the event owner enables it. Must write to R2 the same way the photographer upload path does (REQ-1/REQ-2 apply equivalently).
- **Event cover photo storage** (`events.py` — public cover + owner-authenticated cover-thumbnail): must migrate to R2 the same way originals/thumbnails do (REQ-4/REQ-5 apply equivalently). Lower risk — already served as a direct, unauthenticated URL, unaffected by the read-path architecture decision made in `/design`.

Also found and resolved during analysis (not scope changes, just findings): the non-chunked photographer upload endpoint (`photos.py:91-152` / `uploadPhoto` in `lib/api.ts`) is dead code — never called by the frontend — and is excluded from migration; it should be deleted as unrelated cleanup, not migrated. Event-deletion disk cleanup exists in two independent, duplicated implementations (`purge.py` and `admin.py`) — see `design.md` for the unification approach.

## Out of scope
- Choosing the specific delivery mechanism for reads/writes (presigned-URL redirect vs. backend-proxied streaming) for any given scenario — this is a `/design` decision within the direction the ADR already set.
- Replacing FastAPI `BackgroundTasks` with a real job queue to enable true multi-instance horizontal scaling of face processing — a separate, deferred concern noted in the ADR.
- Any new user-facing feature or UI change — this migration must be functionally invisible to photographers and guests.
- HEIC/RAW file *upload* support — remains out of scope per `photographer-dashboard`'s existing scope; unaffected by this migration.
- Public bucket + custom domain + CDN caching for thumbnails — the ADR explicitly chose presigned URLs over this approach.
- Multi-region or multi-cloud storage redundancy.
- Actually running multiple concurrent backend instances — this migration removes the storage blocker to that; enabling it is separate future work.
- Individual photo deletion or album-triggered file deletion — neither exists as a feature today (album deletion only unassigns photos); only event-level deletion cascades to file purge.

## Open questions
- [ ] OQ-1 (design): Should single-photo downloads redirect to a presigned R2 URL or proxy through the backend? Affects whether the ADR's egress-cost saving is realized for this path. — owner: Engineering
- [ ] OQ-2 (design): Keep the app's existing custom chunk-tracking scheme on top of R2 PutObject calls, or adopt R2/S3's native Multipart Upload API? — owner: Engineering
- [ ] OQ-3 (design): How is the "no partial deletion" purge guarantee (REQ-21) achieved across PostgreSQL + Qdrant + R2 without a native cross-store transaction — retry-to-completion, verification pass, or something else? — owner: Engineering
- [ ] OQ-4 (design): Exact TTL and refresh mechanism for signed read URLs, informed by REQ-10's "must outlast a normal session" requirement and the 24-hour guest session window. — owner: Engineering
- [ ] OQ-5 (design): Backfill migration mechanism/script and maintenance-window scheduling logistics (REQ-17/18/19). — owner: Engineering
- [ ] OQ-6 (design): How ZIP generation meets the 30-second/100-photo bar (REQ-15) against network-fetched R2 objects — e.g., concurrent fetch-and-write into the archive stream. — owner: Engineering

## Acceptance criteria
- AC-1 (Scenario 1): A photographer uploads a 500-photo batch; all photos are stored in R2 and recorded in PostgreSQL, with the same resumability and dedup behavior as today (no visible change in flow).
- AC-2 (Scenario 2): After upload, the face pipeline reads the original from R2, detects faces, and writes a thumbnail to R2; a thumbnail generation failure is logged but does not fail the job.
- AC-3 (Scenario 3): A guest opens the gallery for an event with 120 photos; thumbnails load lazily from R2-backed storage and no photo from another event is ever returned.
- AC-4 (Scenario 4): A guest opens a photo in the lightbox; the preview is generated on first open and served from R2 on subsequent opens without regenerating; the guest never sees a broken image during normal browsing.
- AC-5 (Scenario 5): A guest downloads a single photo; the file arrives with the correct original filename as an attachment, and the photo's download count increments by 1.
- AC-6 (Scenario 6): A guest downloads a ZIP of 100 photos; the archive streams to completion in under 30 seconds and contains all 100 originals under their original filenames.
- AC-7 (Scenario 7): A guest downloads a HEIC-sourced photo; they receive a converted JPEG, generated on first request and served from cache on subsequent requests.
- AC-8 (Scenario 8): After backfill, every photo, thumbnail, preview, and download-cache object that existed on the Railway Volume resolves successfully from R2, with no broken links reported by photographers or guests post-cutover.
- AC-9 (Scenario 9): 30 days after an owner deletes an event (or immediately after an admin force-delete), no R2 objects remain under that event's storage prefix, alongside the existing PostgreSQL/Qdrant purge.
- AC-10 (Scenario 10): When R2 credentials are invalid or the bucket is unreachable, an upload attempt returns a clear, actionable error (not a raw 500) and no partial/inconsistent PostgreSQL record is created.

## Status
Groomed — ready for /design
