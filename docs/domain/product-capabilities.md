# Product Capabilities

Last updated: 2026-06-21

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

## AI Face Processing Pipeline (Epic 4)

**Status:** Shipped — `feat/ai-face-processing`

### What was added

**Backend (`backend/`):**
- Photo upload endpoint: `POST /api/v1/events/{event_id}/photos` — stores file to disk, creates `photos` record with `processing_status = "pending"`, enqueues a `BackgroundTask` before returning 201
- Face pipeline service (`app/services/face_pipeline.py`): InsightFace + ArcFace (lazy-init, CPU-only), 40×40px minimum face filter, atomic idempotency gate (`UPDATE photos ... WHERE status IN ('pending','failed') RETURNING id`), dual-session pattern (gate closes before file I/O and inference), single Qdrant upsert per photo
- Encryption util (`app/utils/crypto.py`): AES-256-GCM encrypt/decrypt; HKDF key derivation from `SECRET_KEY`; nonce + ciphertext + GCM tag stored as `face_records.embedding_enc`
- Qdrant service (`app/services/qdrant.py`): one collection per event (`event_<uuid_hex>`), cosine similarity, 512-dim vectors stored plaintext for search; encrypted copy in PostgreSQL for compliance
- Retry service (`app/services/retry.py`): APScheduler job runs every 5 minutes; resets stuck `processing` jobs (> 15 min old) back to `pending`; retries `failed` photos with `processing_attempts < 5`; permanent `error` after 5 attempts
- Face processing status endpoint: `GET /api/v1/events/{event_id}/face-processing/status` — per-event counts by status (pending / processing / complete / failed / error), photographer-auth required (403 for guests), no cache (live DB query)
- Alembic migration 003: adds `photos` table (with `processing_status`, `face_count`, `processing_attempts`) and `face_records` table (with encrypted embedding, bounding box, Qdrant point ID)
- 28 automated tests covering: crypto round-trip, zero-face, multi-face, 3-face (AC-2 exact), sub-40px filtering, idempotency gates, failure/retry flow, APScheduler retry selection, error logging fields, upload auth, status endpoint counts, guest JWT rejection
