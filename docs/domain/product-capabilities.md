# Product Capabilities

Last updated: 2026-08-15

---

## Event Management (Epic 1)

**Status:** Shipped — `feature/groom-event-management`

### What was added

**Backend (`backend/`):**
- Email+password auth: registration, login, JWT issuance and validation
- Event CRUD: create, read, update, soft-delete; owner-scoped access
- Slug management: auto-generation from bride+groom names, uniqueness enforced at DB level, 422 conflict with suggestions, redirect table for slug changes (301)
- Publish / unpublish: gates on slug + access_mode + cover_photo being set
- Album management: create, rename, delete, ceremony category tags (Ceremony / Sangeet / Mehendi / Haldi / Reception / Family Photos); max 10 per event
- QR code: on-demand PNG generation, streams to client, no disk storage; regenerates automatically when slug changes
- Admin endpoints: paginated event list, suspend / unsuspend, hard delete with full cascade
- APScheduler purge job: runs daily at 02:00, permanently purges events soft-deleted > 30 days ago (photos on disk, Qdrant vectors, PostgreSQL records)

**Frontend (`frontend/`):**
- Auth pages: login, register
- Owner dashboard: event list with status badges
- Event creation form: all required fields, access mode toggle, slug auto-generation from names, 422 suggestion pills
- Event edit page: update any field, publish / unpublish, delete with "type DELETE" confirmation and 30-day recovery messaging
- Album management page: create, rename, delete, ceremony category; album count display
- QR code page: display + download PNG button (proxied via Next.js API route)
- Admin dashboard: paginated all-events table, suspend / unsuspend / hard-delete with confirmation

---

## Guest Access (Epic: guest-access)

**Status:** Shipped — `feature/guest-access`

### What was added

**Backend (`backend/`):**
- Guest authentication endpoint (`POST /api/v1/events/{id}/guest-auth`): handles all three access modes in one call — access-code (case-insensitive), magic-link-otp (6-char system-generated code), public (no code required)
- Guest JWT issuance: `type: guest` discriminator, `sub = event_id`, sliding-window idle expiry via `X-Guest-Token` response header
- Session revocation: `POST /api/v1/events/{id}/revoke-guest-access` sets `guest_access_enabled=false` + `guest_access_revoked_at`; all tokens issued before revocation are rejected on validation
- Re-enable: `POST /api/v1/events/{id}/enable-guest-access`
- In-process `GuestRateLimiter`: per-`(event_id, ip)` lockout after 3 failed attempts; 15-minute cooldown; reset on success

**Frontend (`frontend/`):**
- `app/g/layout.tsx`: minimal no-Nav layout for all guest pages — clean entry and gallery experience
- `app/g/[slug]/page.tsx`: entry page; resolves event by slug, renders access-code or OTP entry form, handles already-authenticated redirect, lockout and revocation error messages, informative unavailable message for non-published events
- `app/g/[slug]/gallery/page.tsx`: auth guard redirects to entry if token missing/expired; placeholder for photo browsing (Album Gallery epic)
- `lib/api.ts` — `guestApiFetch`: guest-token-authenticated fetch helper; reads `X-Guest-Token` response header for sliding-window refresh; clears token on 401
- `lib/auth.ts` — `getGuestToken` / `setGuestToken` / `clearGuestToken` / `isGuestAuthenticated`: per-event guest token management in `localStorage`

---

## Album & Gallery Browsing (Epic 10)

**Status:** Shipped — PR #20 (`feature/album-gallery-browsing`)

### What was added

**Backend (`backend/`):**
- Migration 004: adds `download_count` (INTEGER, default 0), `is_photographer_choice` (BOOLEAN, default false), `thumbnail_path` (TEXT nullable) to `photos`; adds 6 composite gallery indexes covering all sort × filter combinations
- Face pipeline: generates a 600 px-wide WebP thumbnail per photo during processing and stores the SSD-relative path in `thumbnail_path`; failure is non-blocking (face processing continues, thumbnail shows as placeholder)
- `GET /api/v1/events/{id}/gallery` — paginated photo list (50/page); supports `album` filter (ceremony category), `sort` (latest / popular / photographer-choice), `offset` for load-more pagination; returns total count
- `GET /api/v1/events/{id}/gallery/albums` — album tab bar data: All tab + one tab per ceremony category present in the event, each with photo count; zero-count tabs omitted
- `GET /api/v1/events/{id}/photos/{id}/thumbnail` — streams WebP thumbnail from SSD; path-traversal safe; immutable cache headers
- `GET /api/v1/events/{id}/photos/{id}/download` — serves original file as attachment; atomically increments `download_count` only after confirming file exists
- `PATCH /api/v1/events/{id}/photos/{id}/photographer-choice` — owner JWT only; 403 for guest tokens; sets/clears the Photographer Choice flag

**Frontend (`frontend/`):**
- `app/g/[slug]/gallery/page.tsx`: full gallery page replacing the "coming soon" stub; auth guard preserved; URL state sync (`?album=&sort=&limit=`) with full restore on refresh/share; responsive 2–5 column thumbnail grid; Load More button (hidden when all photos loaded)
- `components/gallery/AlbumFilterBar.tsx`: horizontal scrollable tab bar with per-album photo count badges; active tab highlighted
- `components/gallery/SortSelector.tsx`: dropdown for Latest / Popular / Photographer Choice
- `components/gallery/PhotoThumbnail.tsx`: fetches thumbnail as authenticated blob URL; gray pulse placeholder while loading or when pipeline pending; gold ✦ badge on Photographer's Choice photos
- `components/gallery/Lightbox.tsx`: full-screen overlay; loads thumbnail blob for display; Prev/Next navigation with automatic next-batch fetch at list boundary; keyboard (Escape/Arrow keys); Download button (calls `/download`, triggers browser save); scroll position restored on close
- `lib/api.ts` — `guestFetchBlob`: binary fetch helper for thumbnail/download endpoints; `getGalleryAlbums` / `getGalleryPhotos`: typed gallery API calls

---

## Face Recognition Search (Epic 5)

**Status:** Shipped — `feature/face-recognition-search`

### What was added

**Backend (`backend/`):**
- `POST /api/v1/events/{id}/search` — multipart selfie upload; extracts ArcFace embedding with InsightFace, vector-searches Qdrant, returns ranked photo list; 20 MB limit enforced before any processing; 401 on invalid/expired guest JWT
- Dominant-face selection: when multiple faces detected, proceeds with the highest-confidence face if its `det_score` gap over the next is ≥ 0.10; otherwise returns `422 no_dominant_face`; zero faces returns `422 no_face_detected`
- Selfie deletion guarantee: `selfie_bytes` copied into memory, `UploadFile` closed (temp file deleted) before extraction; `del selfie_bytes` called in `try/finally` so no bytes survive an extraction error
- `app/services/face_search.py` — orchestrates embedding extraction, dominant-face selection, Qdrant search, photo dedup (highest score per photo), DB photo fetch, thumbnail URL construction
- `app/services/search_cache.py` — in-memory `SearchCache` singleton keyed by `(sid, sha256(selfie_bytes))`; 1-hour TTL with lazy eviction; `X-Search-Cache: hit|miss` response header
- `app/services/qdrant.py` — added `search_faces(event_id, embedding, score_threshold, limit)` for vector similarity search
- Guest JWT gains stable `sid` claim (UUID) generated at login and threaded unchanged through all token refreshes; used as the per-session cache scope
- `app/config.py` — three new deployment-level config values: `FACE_SEARCH_SCORE_THRESHOLD` (0.4), `FACE_SEARCH_RESULT_CAP` (50), `FACE_SEARCH_CACHE_TTL_SECONDS` (3600)
- `app/services/face_pipeline.py` — `_detect_faces` now returns `det_score` alongside `bbox` and `embedding`

**Frontend (`frontend/`):**
- `app/g/[slug]/search/page.tsx` — search page (slug-keyed; supersedes the original `app/events/[eventId]/search/page.tsx`, removed as dead code); state machine `idle → uploading → results | error`; clears stale results immediately on new upload
- `components/search/SelfieUpload.tsx` — file input (`image/jpeg,image/png`), `capture="user"` for mobile camera; client-side 20 MB pre-check; loading spinner during upload; raw `fetch` multipart POST; refreshes guest token from `X-Guest-Token` header
- `components/search/SearchResults.tsx` — ranked photo grid (API order = match rank); authenticated blob URL thumbnails via `guestFetchBlob`; "no photos found" empty state; "Try another photo" button
- `components/search/SearchError.tsx` — maps `no_face_detected`, `no_dominant_face`, `file_too_large`, and unknown codes to user-friendly messages

---

## Gallery Guest Actions

**Status:** Shipped — `feature/gallery-guest-actions`

### What was added

**Frontend (`frontend/`):**
- `components/gallery/PhotoThumbnail.tsx`: restructured to `<div>` + inner `<button>` to support an action overlay; FavouriteToggle (heart) and ShareButton (copy link) appear as a bottom-right overlay — always visible on mobile, hover-visible on desktop; Photographer's Choice badge moved to outer div with `pointer-events-none`
- `components/gallery/Lightbox.tsx`: FavouriteToggle and ShareButton added to top bar alongside the existing Download button; isFavourited/onToggleFavourite props thread through from the gallery page
- `app/g/[slug]/gallery/page.tsx`: wired `useFavourites` hook; gallery header extended with "Find my photos" blue pill link (→ search page) and "Favourites" link with live count badge; isFavourited + toggle callbacks passed to every PhotoThumbnail and the Lightbox
- `app/g/[slug]/search/page.tsx`: new guest face search page; auth guard (redirects unauthenticated guests to event entry); state machine renders SelfieUpload → SearchResults | SearchError; token refresh persisted to both localStorage and local state; Suspense wrapper matching gallery pattern

---

## Privacy & Security (Epic: privacy-security)

**Status:** Shipped — `feature/privacy-security-design`

Governance layer over the existing encryption + selfie-deletion controls. Compliance frame: India's DPDP Act 2023 (platform = Data Fiduciary, guests = Data Principals).

### What was added

**Backend (`backend/`):**
- Owner consent at publish: `publish_event` writes a `consent_records` row (event_id, confirmed_by, confirmed_at) server-side using the authenticated owner identity — no API contract change; republish writes a fresh record
- Guest face-search rate limiting: in-process sliding-window limiter (10 req / 5 min) keyed on the JWT `sid`, enforced as a route dependency on `POST /events/{id}/search`; returns 429 + `Retry-After` on breach (selfie-upload ≡ search is one endpoint)
- Consent precondition: `/search` now requires a `consent_ack` form field (422 `consent_required` if absent/false); emits a non-PII structured audit log line (event_id, sid, timestamp only)
- Face-data removal requests: guest-authenticated `POST /events/{id}/removal-requests` (name, email, description); admin `GET /admin/removal-requests` (with pending count) and `POST /admin/removal-requests/{id}/fulfill`; records never deleted, retained ≥3y
- Encryption audit endpoint: admin-only `GET /internal/audit/embedding-encryption` (off the public `/api/v1` prefix) verifies PostgreSQL `face_records.embedding_enc` is non-null + decryptable (not Qdrant — see ADR)
- HSTS: `Strict-Transport-Security` header (max-age 1y) on all responses; TLS termination is the proxy's responsibility
- New tables `consent_records` / `removal_requests` use bare UUID columns with NO foreign key, so they survive the 30-day event purge cascade (ADR 2026-06-23)

**Frontend (`frontend/`):**
- Publish pre-flight consent checkbox (unchecked, gates the publish button; re-required on republish)
- Selfie screen privacy notice + "I understand, continue" gate carrying the 18+/guardian affirmation; camera inert until acknowledged; sends `consent_ack=true`
- `SelfieUpload` 429 handling: reads `Retry-After`, shows a human-readable wait message (no raw status code)
- "Remove my face data" link + form (name, email, description) on the guest gallery page with on-screen confirmation
- Static `/privacy` page (no API call): DPDP §6 legal basis, Data Fiduciary identity, 30-day retention, consent-withdrawal + removal instructions
- Admin dashboard: pending removal-request count badge + list with "Mark fulfilled" action

---

## Admin Platform & Analytics (Epic: admin-platform)

**Status:** Shipped — `feature/admin-platform-analytics`

Reconciled two gaps found in already-shipped admin code (Event Management #12) and added the four scenarios that were previously nothing-built: processing monitor, failure-rate alerting, event-owner analytics, platform health dashboard.

### What was added

**Backend (`backend/`):**
- Admin event list (`GET /admin/events`) now returns `photo_count`, `storage_used_bytes` (original bytes only), and `last_activity_at` per event via one aggregated query (no N+1); supports `?status=` filter and `?sort=last_activity|photo_count`
- Admin hard delete now calls the real `qdrant.delete_collection()` (idempotent on 404) instead of the pre-existing `_stub_qdrant_delete` — a hard-deleted event's face embeddings are actually removed from Qdrant now
- New admin event detail endpoint (`GET /admin/events/{id}`): context fields + a 5-state processing monitor (`pending`/`processing`/`complete`/`failed`/`error` — `failed` is retryable, `error` is exhausted-retries)
- New platform health dashboard (`GET /admin/health`): total events/photos/storage, 24h processing error rate
- New automated failure-rate alerting: APScheduler job every 5 minutes, emails every `is_admin=true` user when an event's 1-hour failure rate exceeds 10%; in-process dedup (no repeat alert for the same event within 1 hour) — see ADR `2026-08-15-admin-alert-in-process-dedup`
- New event-owner analytics (`GET /events/{id}/analytics`, owner-only): total views/downloads/searches
- Three new event-scoped tables (`view_events`, `download_events`, `search_events` — no guest identity, CASCADE-deleted with the event); new guest-facing view beacon (`POST /events/{id}/photos/{id}/view`); download events written on single-photo and ZIP download completion (one row per ZIP request, not per photo); search events written on every completed search including cache hits

**Frontend (`frontend/`):**
- Admin dashboard: platform-health stat cards; storage/last-activity columns on the event table; event name links to a new detail page
- New admin event detail page (`/admin/events/[eventId]`): context fields + processing monitor grid
- Event owner's event detail page: new analytics section (views/downloads/searches)
- Lightbox fires the view beacon once per photo opened (fire-and-forget, not on every re-render)
- New shared `lib/format.ts` helpers (bytes, datetime, percent) — see ADR `2026-08-15-shared-format-helpers`

---

## Guest Uploads

**Status:** Shipped — `feature/guest-uploads`

Lets wedding guests contribute their own photos to the event gallery, no app/account/sign-up — reuses every existing piece of infrastructure (guest access gate, storage, face pipeline, gallery) with no new service or trust boundary. See ADR `2026-08-19-guest-upload-per-file-requests` for why uploads are sent as independent per-file requests rather than a single batch or the photographer's chunked/resumable session.

### What was added

**Backend (`backend/`):**
- Migration 010: `events.guest_uploads_enabled` (BOOLEAN, default true), `photos.uploaded_by` (`"photographer" | "guest"`, default `"photographer"`), `photos.guest_display_name` (nullable free text)
- `POST /api/v1/events/{id}/guest-uploads` — guest-JWT-authenticated multipart upload; one file per request; reuses `get_validated_guest_event` (access gate + revocation), the `ALLOWED_CONTENT_TYPES`/`MAX_FILE_SIZE` constants from `photos.py`, and the same `background_tasks.add_task(process_photo, ...)` call as photographer uploads — guest photos enter the identical async face-processing pipeline, no special-casing
- New in-process `GuestUploadCounter` (`app/services/guest_auth.py`), same pattern as the existing `GuestRateLimiter`: per-`(event_id, sid)` cap of 20 accepted uploads per session; only successfully committed uploads count against the cap
- Owner toggle: `guest_uploads_enabled` on `EventOut`/`EventUpdate`, edited via the existing `PUT /{id}` (no dedicated action endpoint — unlike guest-access revocation, this flag has no session-invalidation side effect); also exposed on `EventPublicOut` so the guest-facing gallery knows whether to show the upload CTA
- `GalleryPhotoOut` and `PhotoOut` both gain `uploaded_by` / `guest_display_name`, so album assignment and Photographer's Choice already work on guest photos with zero extra code — they're source-agnostic

**Frontend (`frontend/`):**
- `components/gallery/GuestUploadModal.tsx`: bottom-sheet modal (mirrors the "Remove my face data" modal pattern) — optional display-name field, native multi-file picker, client-side 25 MB/JPEG-PNG pre-validation, 20-file client-side cap warning, 3-way concurrent per-file upload with per-file status, completion summary
- `lib/api.ts` — `uploadGuestPhoto`: raw-fetch multipart pattern (per the `2026-06-20-selfie-upload-raw-fetch` ADR), refreshes `X-Guest-Token`, clears the guest token on 401
- Guest gallery page: "Upload your photos" CTA shown only when `event.guest_uploads_enabled`
- `PhotoThumbnail.tsx` / `Lightbox.tsx`: "Guest photo · {name}" badge (falls back to "Guest") when `uploaded_by === 'guest'`
- Owner event detail page: "Guest Uploads: On/Off" toggle card, mirroring the Guest Access card, calling `updateEvent` directly

---

## Infrastructure & Reliability Hardening

**Status:** Shipped — same-day follow-up after the Guest Uploads launch, triggered by production bug reports while verifying the release

A cluster of fixes found by actually testing Guest Uploads end-to-end on production and on a real phone, rather than issues in the feature itself.

### What changed

**Backend (`backend/`):**
- **Backend now served from `api.picslelo.com`**, a custom domain on the Railway service, instead of the shared `backend-production-*.up.railway.app` subdomain. Some mobile carriers block or fail to resolve Railway's shared domain pool — this was silently breaking every API call (gallery load, login, registration) on affected cellular networks while wifi/desktop worked fine. DNS: CNAME `api` → the Railway-provided target, TXT `_railway-verify.api` for ownership verification; the raw `*.up.railway.app` URL still works as a fallback.
- **CORS fix**: `allow_credentials` set to `False` in `CORSMiddleware` (was `True` alongside `allow_origins=["*"]`, a combination the CORS spec forbids). This app authenticates entirely via Bearer tokens (owner JWT, guest JWT) — never cookies — so credentialed CORS was never actually needed. Starlette only swapped the wildcard origin for an explicit one on requests carrying a `Cookie` header, so every real response kept advertising the forbidden `* ` + `allow-credentials: true` combination; Chrome tolerated it, Safari/WebKit rejected the response outright.
- **EXIF orientation fix**: `_generate_thumbnail` (`app/services/face_pipeline.py`) now calls `ImageOps.exif_transpose()` before resizing. Phone photos shot in portrait store landscape sensor pixels plus an EXIF rotation tag; the WebP thumbnail (which carries no EXIF) was baking in the wrong orientation, so portrait photos displayed sideways/upside-down in the gallery grid and lightbox even though the original downloadable file was fine. All existing production thumbnails were regenerated in place from their originals (derived files only — originals and DB rows untouched).

**Frontend (`frontend/`):**
- Guest gallery header now stacks/wraps on narrow phone widths (`flex-col` below `sm:`) instead of colliding with the "Upload your photos" CTA that Guest Uploads added; same fix applied to the global `Nav` bar, which had never wrapped on any page.
- `apiFetch` now attaches the HTTP status to thrown errors. The guest entry page (`/g/[slug]`) distinguishes a genuine 404 ("Event not found") from a transient failure like a 5xx or network error ("Something went wrong" + a **Try again** retry button) — previously any fetch failure at all showed the permanent-sounding "Event not found" message.
- `NEXT_PUBLIC_API_URL` now points at `https://api.picslelo.com`.
