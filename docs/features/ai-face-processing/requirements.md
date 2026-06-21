**Status:** Groomed — ready for /design

## Epic
docs/epics/ai-face-processing/EPIC.md

## Purpose
Automatically detect faces in every imported wedding photo, generate ArcFace embeddings, and store them in a scoped vector database — so that guests can later find their own photos via selfie search without any manual tagging by the photographer.

## Scenarios in scope
1. Photo uploaded → face detection and embedding runs asynchronously after the upload response is returned
2. Multiple faces detected in one photo → one face record and one Qdrant vector per detected face
3. No face detected in a photo → photo marked as zero-face, no embeddings stored, no error surfaced to the uploader
4. Processing job fails (InsightFace error or Qdrant write error) → job marked `failed`, logged with context, retried on next APScheduler run
5. Processing job re-runs on an already-processed photo → existing records retained, no duplicate embeddings created
6. Photographer (or event owner) monitors face processing status → queue depth shown as counts per processing state per event

## User stories / use cases
- As a photographer, I want face processing to start automatically after I upload photos, so that I do not need to trigger it manually.
- As a photographer, I want to upload photos and receive an immediate response, so that I can continue uploading without waiting for AI processing to complete.
- As a photographer, I want photos with multiple people to have every face indexed independently, so that each guest can find themselves regardless of group shots.
- As a photographer, I want landscape or detail shots (no faces) to be silently accepted and marked accordingly, so that my upload is not interrupted by false errors.
- As a photographer, I want failed processing jobs to be retried automatically, so that transient errors do not leave photos permanently unindexed without my intervention.
- As a photographer, I want to see how many photos are pending, indexed, and failed, so that I know when the gallery is guest-ready.
- As an event owner, I want face embeddings to be stored only within my event's scope, so that guest data cannot leak to other events.

## Functional requirements

### Scenario 1 — Asynchronous face processing after upload
1. REQ-1 (Scenario 1): After a photo file is persisted to storage and metadata is recorded in PostgreSQL, the backend must enqueue a face-processing job as a FastAPI `BackgroundTask` before returning the upload HTTP response.
2. REQ-2 (Scenario 1): The upload HTTP response must not wait for face detection or embedding to complete — the pipeline runs entirely after the response is sent.
3. REQ-3 (Scenario 1): Each newly enqueued photo must have its `processing_status` set to `pending` on the `photos` record at enqueue time. `face_records` rows are only created after processing completes successfully.
4. REQ-4 (Scenario 1): Face detection must use InsightFace with ArcFace embedding (512-dimensional vectors); faces smaller than 40×40 pixels must be skipped.

### Scenario 2 — Multiple faces per photo
5. REQ-5 (Scenario 2): When InsightFace detects more than one face in a photo, the backend must create one `face_records` row and one Qdrant vector point per detected face.
6. REQ-6 (Scenario 2): Each face record must store: `photo_id`, `event_id`, a bounding box, and a reference to its Qdrant point ID.
7. REQ-7 (Scenario 2): All face vectors from a single photo are written in a single Qdrant upsert operation to reduce round trips; the photo's processing status must only be set to `complete` after all faces are successfully stored.
8. REQ-8 (Scenario 2): The `photos` record must store the total count of detected faces (`face_count`) once processing completes.

### Scenario 3 — No face detected
9. REQ-9 (Scenario 3): When InsightFace returns zero detected faces for a photo, the backend must set `face_count = 0` on the `photos` record and set the photo's processing status to `complete`.
10. REQ-10 (Scenario 3): No `face_records` rows and no Qdrant vectors must be written for a zero-face photo.
11. REQ-11 (Scenario 3): The zero-face outcome must not surface an error to the photographer in the upload response or in the dashboard status summary.

### Scenario 4 — Processing job failure and retry
12. REQ-12 (Scenario 4): If the face-processing job raises an exception (InsightFace error, Qdrant write failure, or any unhandled error), the photo's processing status must be set to `failed` in `face_records`.
13. REQ-13 (Scenario 4): Each failure must be logged with at minimum: `event_id`, `photo_id`, exception type, and a stack trace.
14. REQ-14 (Scenario 4): Failed photos must be retried by APScheduler on its next scheduled run; the retry must not require manual action by the photographer.
15. REQ-15 (Scenario 4): While a photo is actively being processed, its status must be `processing`; it must transition to `complete` or `failed` upon job completion.

### Scenario 5 — Idempotent re-processing
16. REQ-16 (Scenario 5): Before running face detection on a photo, the backend must check whether `face_records` already contains completed entries for that `photo_id`.
17. REQ-17 (Scenario 5): If completed records exist, the job must exit without modifying any existing `face_records` rows or Qdrant vectors.
18. REQ-18 (Scenario 5): If a photo is in `processing` status (picked up by a concurrent or previous run that did not complete), the re-entrant job must not create duplicate vectors; the implementation strategy is a design decision.
19. REQ-19 (Scenario 5): Idempotency must hold across backend restarts — a photo that was fully indexed before a restart must not be re-processed after restart.

### Scenario 6 — Processing status monitoring
20. REQ-20 (Scenario 6): The backend must expose an endpoint that returns, per event: count of photos in each processing state (`pending`, `processing`, `complete`, `failed`) and the total photo count.
21. REQ-21 (Scenario 6): The endpoint must require photographer or event-owner authentication; guest-scoped sessions must receive a 403.
22. REQ-22 (Scenario 6): The status counts must reflect the current state at query time; stale cached values older than 5 seconds are not acceptable.

## Non-functional requirements
- NFR-1: Face processing must operate CPU-only on the single 4-core / 16 GB RAM VM; no GPU is required or assumed.
- NFR-2: AES-256 encryption must be applied to face embedding vectors before they are stored in Qdrant; the encryption key is sourced exclusively from the `SECRET_KEY` environment variable and must not be stored in the database.
- NFR-3: All Qdrant vector searches and writes must be scoped to the event's dedicated Qdrant collection — one collection per event — so that face data from one event is never accessible from another event's collection.
- NFR-4: The face processing pipeline must not degrade upload throughput; upload latency must not increase as a function of pending face jobs.
- NFR-5: APScheduler retry runs must not overlap with in-progress BackgroundTask jobs for the same photo (no concurrent duplicate processing).
- NFR-6: Processing a single photo must be atomic with respect to `face_records` and Qdrant — either all face vectors for that photo are committed and the status is `complete`, or none are committed and the status remains `pending` or `failed`.

## Context
- Face processing is implemented as FastAPI `BackgroundTask` (in-process, same VM process), not a separate Celery or Redis-backed worker queue.
- APScheduler runs within the same process and is used solely for retrying `failed` photos; it is not the primary job dispatcher.
- Qdrant is hosted on Qdrant Cloud (free tier); one collection is created per event. Collection creation and deletion are lifecycle operations managed by the backend (Event Management epic).
- The 40×40 pixel minimum face size is the InsightFace default; faces below this threshold are silently skipped and do not produce a `face_records` entry.
- Guest selfie search (consuming the embeddings) is out of scope here and is covered by the Face Recognition Search epic.
- The photographer dashboard's display of processing counts (REQ-20 to REQ-22) consumes this feature's status endpoint; the dashboard UI itself is covered by the Photographer Dashboard epic.
- Architecture constraints that apply here: upload must never block on face processing (constraint 1); embeddings encrypted at rest (constraint 2); searches scoped per `event_id` (constraint 3); backend owns all data stores (constraint 5); face jobs must be idempotent (constraint 6). Full constraint declaration: `docs/architecture/constraints.md`.

## Out of scope
- GPU acceleration — CPU-only for MVP
- Distributed task queue (Celery, Redis, RQ) — BackgroundTasks and APScheduler only
- Real-time push notifications or webhooks for processing completion — monitoring is pull-based (polling or SSE is a design decision for the dashboard)
- Admin alerting on sustained failure rates — covered by the Admin Platform epic
- Face recognition search (consuming the stored embeddings) — covered by the Face Recognition Search epic
- HEIC and RAW file format support
- Face clustering or automatic grouping of the same person across photos

## Open questions
- [x] Should the Qdrant collection be named by `event_id` slug or by a human-readable event name? — owner: Engineering — **resolved:** `event_<uuid_no_dashes>` (stable across event slug renames). See design.md.
- [x] What AES encryption mode is used for embedding encryption — CBC (with IV) or GCM (with authentication tag)? — owner: Engineering — **resolved:** AES-256-GCM; 96-bit nonce prepended to ciphertext. See design.md.
- [x] Should failed photos surface a visible per-photo error status to the photographer in the dashboard, or appear only as an aggregate failed count? — owner: Product Team — **resolved:** per-photo `failed`/`error` status exposed via the status endpoint; not aggregate-only.
- [x] What is the retry cap — how many consecutive failures before a photo is permanently marked `error`? — owner: Engineering — **resolved:** 5 attempts; `processing_attempts >= 5` → permanent `error` state, excluded from all future APScheduler runs.

## Acceptance criteria
- AC-1 (Scenario 1): Given a photo is uploaded and stored, the upload HTTP response is returned before face detection begins, and the `photos` record has `processing_status = "pending"` within the same request lifecycle. No `face_records` row exists yet at this point.
- AC-1b (Scenario 1): Given a photo is enqueued for processing, face detection runs via InsightFace with ArcFace in the background after the response is sent.
- AC-2 (Scenario 2): Given a photo containing three distinct faces, processing produces exactly three `face_records` rows and three Qdrant vector points, all linked to the same `photo_id`.
- AC-2b (Scenario 2): Given processing completes successfully for a multi-face photo, the `photos` record shows `face_count = 3` and processing status `complete`.
- AC-3 (Scenario 3): Given a photo with no detectable faces, processing completes without error, the `photos` record shows `face_count = 0` and status `complete`, and zero `face_records` rows are created.
- AC-3b (Scenario 3): Given a zero-face photo, no error appears in the upload response or in the photographer's processing status view.
- AC-4 (Scenario 4): Given a Qdrant write error during processing, the photo's status is set to `failed`, the error is logged with `event_id` and `photo_id`, and no partial vectors remain in Qdrant for that photo.
- AC-4b (Scenario 4): Given a photo is in `failed` status, the next APScheduler run picks it up and attempts processing again without manual intervention.
- AC-5 (Scenario 5): Given a photo that already has status `complete` and existing `face_records`, re-running the processing job results in no new `face_records` rows and no new Qdrant vectors.
- AC-5b (Scenario 5): Given the backend restarts while a photo was mid-processing (status `processing`), after restart no duplicate embeddings are written for that photo.
- AC-6 (Scenario 6): Given an event with 10 photos (7 complete, 2 pending, 1 failed), the status endpoint returns exactly those counts for that event.
- AC-6b (Scenario 6): Given a guest-scoped session calls the status endpoint, the response is 403 Forbidden.
- AC-6c (Scenario 6): Given a photo transitions from `pending` to `complete`, the status endpoint reflects the updated count within 5 seconds.
