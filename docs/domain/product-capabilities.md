# Product Capabilities

Last updated: 2026-06-20

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
- `app/events/[eventId]/search/page.tsx` — search page; state machine `idle → uploading → results | error`; clears stale results immediately on new upload
- `components/search/SelfieUpload.tsx` — file input (`image/jpeg,image/png`), `capture="user"` for mobile camera; client-side 20 MB pre-check; loading spinner during upload; raw `fetch` multipart POST; refreshes guest token from `X-Guest-Token` header
- `components/search/SearchResults.tsx` — ranked photo grid (API order = match rank); authenticated blob URL thumbnails via `guestFetchBlob`; "no photos found" empty state; "Try another photo" button
- `components/search/SearchError.tsx` — maps `no_face_detected`, `no_dominant_face`, `file_too_large`, and unknown codes to user-friendly messages
