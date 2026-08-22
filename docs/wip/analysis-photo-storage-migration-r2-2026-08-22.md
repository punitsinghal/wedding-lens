## Impact Analysis: Photo storage migration — Railway Volume → Cloudflare R2
Date: 2026-08-22

## Change
Current: All photo bytes (originals, thumbnails, previews/"lightbox" tier, HEIC-download-conversion cache, event cover photos) live on the Railway Volume at `STORAGE_PATH`, read/written via direct local filesystem calls, served to clients via FastAPI `FileResponse`/`StreamingResponse`.

Proposed: Same object taxonomy, stored in Cloudflare R2 instead, per `docs/decisions/2026-08-22-cloudflare-r2-photo-storage.md`. That ADR assumed backend-issued presigned URLs for both upload and read, so bytes flow directly client↔R2 rather than through the backend, in order to capture R2's $0/GB egress benefit.

Classification: **Breaking — owned.** Every consumer is inside this repo (backend + frontend); there is no external API consumer. However, the actual blast radius is substantially larger than assumed at grooming time (see Scope gaps below), and the specific migration pattern chosen (presigned URLs vs. backend-proxy) changes this from a contained backend-only change to a cross-cutting frontend change touching 8+ components. This is the central finding of this analysis.

## Consumers found

### Backend — local-disk read/write call sites (all "Owned")
| Location | File:line | Classification | Action needed |
|---|---|---|---|
| Photographer single-photo upload | `backend/app/routers/photos.py:102,124` | Owned | Write to R2 instead of disk |
| **Guest single-photo upload (scope gap — not in groomed requirements)** | `backend/app/routers/guest_uploads.py:87-89` | Owned | Write to R2 instead of disk |
| Chunked upload — chunk write | `backend/app/routers/uploads.py:257` | Owned | Write chunk to R2 (or R2 multipart) |
| Chunked upload — assembly | `backend/app/routers/uploads.py:322-326` | Owned | Assemble in R2, not via local `shutil.copyfileobj` |
| Chunked upload — magic-byte re-validation | `backend/app/routers/uploads.py:340-342` | Owned | Re-validate from R2-read bytes |
| Thumbnail generation (read original + write thumbnail) | `backend/app/services/face_pipeline.py:118-121,140-141` | Owned | Read original from, write thumbnail to R2 |
| Lightbox/preview generation (read original + write preview) | `backend/app/services/gallery.py:130-148` | Owned | Read/write via R2 |
| HEIC→JPEG download-conversion cache | `backend/app/services/gallery.py:208-245` | Owned | Read/write via R2 |
| ZIP bulk download assembly | `backend/app/services/zip_streaming.py:57-76` | Owned | **Hardest call site** — `zipfile.ZipFile.write(path)` requires a real local path; needs per-photo R2 fetch into memory/temp file before zipping |
| Thumbnail serve endpoint | `backend/app/routers/gallery.py:81-103` (`FileResponse`) | Owned | Redirect to signed URL, or proxy-stream from R2 |
| Lightbox serve endpoint | `backend/app/routers/gallery.py:106-142` (`FileResponse`) | Owned | Same as above |
| Single-download serve endpoint | `backend/app/routers/gallery.py:145-191` (`FileResponse`) | Owned | Same as above |
| Photographer "preview" (actually thumbnail) endpoint | `backend/app/routers/photos.py:332-360` (`FileResponse`) | Owned | Same as above |
| **Event cover photo endpoint (scope gap)** | `backend/app/routers/events.py:78-104` (`FileResponse`, public/unauthenticated) | Owned | Same as above — already used as a plain `<img src>`/CSS background today, so a signed R2 URL drops in with zero frontend change |
| **Event cover-thumbnail endpoint (scope gap)** | `backend/app/routers/events.py:146-167` (`FileResponse`, owner-authenticated) | Owned | Same as above |
| Event-deletion purge (30-day grace) | `backend/app/services/purge.py:66-68` (`shutil.rmtree`) | Owned | Delete R2 objects under `events/{event_id}/` prefix |
| **Admin hard-delete purge — duplicate logic (scope gap)** | `backend/app/routers/admin.py:208-220` (`shutil.rmtree`, independent of `purge.py`) | Owned | Must be migrated in lockstep with `purge.py`, or unified into one function first |
| Abandoned chunk-upload cleanup | `backend/app/services/purge.py:145-148` | Owned | Delete R2 tmp objects/multipart parts instead of local tmp dir |

### Frontend — URL construction/consumption (all "Owned")
| Location | File:line | Pattern | Action needed if URLs become presigned |
|---|---|---|---|
| `PhotoThumbnail` (gallery grid) | `frontend/components/gallery/PhotoThumbnail.tsx:32,60` | `guestFetchBlob` + Bearer auth → blob → `<img src={blobUrl}>` | Rewrite to `<img src={signedUrl}>` directly, drop blob-fetch |
| Favourites grid | `frontend/app/g/[slug]/favourites/page.tsx:30` | Same pattern | Same |
| Face-search results grid | `frontend/components/search/SearchResults.tsx:31` | Same pattern | Same |
| Photographer upload/manage grid | `frontend/app/events/[eventId]/photos/page.tsx:92` (`ownerFetchBlob`) | Same pattern | Same |
| Album detail grid | `frontend/app/events/[eventId]/albums/[albumId]/page.tsx:59` (`fetchAuthedBlob`) | Same pattern | Same |
| Event dashboard cover-photo picker | `frontend/app/events/[eventId]/page.tsx:153` (`fetchAuthedBlob`) | Same pattern | Same |
| Lightbox full-res/preview image | `frontend/components/gallery/Lightbox.tsx:47,150` | Hand-built `/lightbox` path + `guestFetchBlob` → blob → `<img>` | Same, plus: hand-built path assumption must be replaced by a field from the API response |
| Share-page photo view | `frontend/app/share/[token]/page.tsx:66-67,134-138` | Hand-built `/thumbnail` path + `guestFetchBlob` → blob → `<img>` | Same as Lightbox |
| Single-photo download | `frontend/lib/api.ts:597-622` (`downloadPhoto`) | `fetch` hardcoded `/download` endpoint → blob → synthetic `<a>` click | Low risk if endpoint keeps streaming bytes; needs rewrite only if backend switches to returning a JSON `{download_url}` |
| Bulk ZIP downloads | `frontend/lib/api.ts:569-595,831-856` | `fetch` hardcoded `/zip` endpoints → blob → synthetic `<a>` click | No change needed — ZIP is unavoidably backend-proxied either way |
| Event cover photo | `frontend/lib/api.ts:319-321` (`getEventCoverUrl`) | Hand-built URL, already used directly in `<img src>`/CSS (unauthenticated) | No change needed regardless of migration pattern chosen |

**Cross-cutting finding:** `docs/decisions/2026-06-20-authenticated-image-blob-url-pattern.md` documents *why* the frontend fetches every authenticated image via `fetch()`+Bearer-header+`blob()`+`createObjectURL()` instead of a plain `<img src>` — because `<img>` can't carry an `Authorization` header. A presigned R2 URL is self-authenticating via its query-string signature and is *meant* to be used directly in `<img src>`; carrying a `Bearer` header to a presigned URL is unnecessary and could trigger CORS issues. **This means the presigned-URL approach doesn't just add work — it obsoletes an existing, deliberate ADR** and requires touching 8 frontend components that currently implement it correctly for the old model.

## Scope gaps found (not covered by `docs/features/photo-storage-migration/requirements.md`)
Grooming derived scenarios from existing `docs/features/*/requirements.md` files, none of which document these two real, live features:
1. **Guest photo uploads** — a live, event-owner-toggleable feature (`guest_uploads_enabled`), with its own upload endpoint, its own frontend modal (`GuestUploadModal.tsx`), sharing the same local-disk write pattern as the photographer's non-chunked upload path. Not chunked — single-request upload.
2. **Event cover photo storage** — two endpoints (public cover, owner-authenticated cover-thumbnail) serving files from the same `STORAGE_PATH`, used on the public event landing page and the owner dashboard. Lower risk (already a direct-URL, unauthenticated pattern for the public one) but must still be migrated.

Also found: a **non-chunked photographer single-photo upload endpoint** (`photos.py:91-152`) exists alongside the chunked flow in `uploads.py` — unclear from this analysis alone whether this is legacy/unused by the current frontend or an active alternate path; worth confirming during design.

And: **event-deletion disk cleanup is implemented twice**, independently, in `purge.py` (30-day grace period) and `admin.py` (admin hard-delete) — a pre-existing duplication risk that this migration will make worse if only one copy is updated.

## Migration path

The central fork is **how reads are delivered**, and it determines how much of the rest of this migration costs:

**Option A — Presigned URLs end-to-end (bytes bypass the backend for reads and writes)**
Realizes the ADR's full egress-cost savings. Requires: retiring the authenticated-blob-URL pattern and rewriting all 8 frontend image-display call sites to consume a URL field directly in `<img src>`; adding `thumbnail_url`/`lightbox_url`/etc. fields to API responses instead of relative paths; configuring R2 CORS; deciding presigned URL TTL vs. session length (per groomed REQ-10); ZIP generation still must proxy through the backend regardless (R2 has no server-side "combine into archive" primitive).

**Option B — Backend-proxied reads (R2 only replaces the disk under existing endpoints)**
Existing `FileResponse`/blob-fetch pattern is preserved untouched on the frontend — zero frontend changes for reads. Backend endpoints internally fetch from R2 and stream to the client exactly as they stream from disk today. Ships faster, lower risk, fully backward-compatible with the existing auth-blob-URL ADR. **Forfeits most of the egress-cost savings** — Railway still bills $0.05/GB on the backend→guest leg for every thumbnail, preview, and download, same as today. Only removes the disk-capacity and horizontal-scaling blockers, not the cost driver.

**Option C — Hybrid**: presigned URLs only for already-unauthenticated, already-direct-URL content (event cover photo — zero frontend change either way), backend-proxied for everything requiring guest/owner auth (thumbnails, lightbox, downloads). Captures a slice of the egress savings (cover photos are fetched by every gallery visit) with none of the 8-component frontend rewrite; leaves the door open to migrate individual endpoints to presigned URLs later once real egress cost is measured.

Uploads are a separate, lower-risk fork: presigned PUT for chunk/single-photo upload is straightforward regardless of which read option is chosen, since there's no existing "upload via blob pattern" to unwind — only `initiateUpload`/`uploadChunk`/`completeUpload` in `lib/api.ts`, already designed around a session/URL exchange.

## Recommendation
Proceed, but the read-path decision (A/B/C above) needs to be made explicitly in `/design` before implementation starts — it changes the frontend blast radius from "zero files" to "8+ components plus one retired ADR." Also recommend folding the two scope gaps (guest uploads, event cover photos) into the migration's implementation scope now rather than discovering them mid-build; they don't need new user-facing requirements (same storage pattern as already-groomed scenarios), so a lightweight requirements addendum is sufficient rather than a full re-groom.

## Open questions
- [ ] Is the non-chunked photographer upload endpoint (`photos.py:91-152`) still live/used, or dead code superseded by the chunked flow? — owner: Engineering
- [ ] Should `purge.py` and `admin.py`'s duplicated event-deletion disk cleanup be unified into one function as part of this migration (recommended, to avoid migrating the same logic twice and having them drift)? — owner: Engineering
- [ ] Read-path pattern: Option A, B, or C above? — owner: Punit (architecture decision, session in progress)
