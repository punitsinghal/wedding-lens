# AI Face Processing Pipeline — Test Plan

**Feature:** AI Face Processing Pipeline
**Branch:** `feat/ai-face-processing`
**Date:** 2026-06-20
**Requirements:** [requirements.md](./requirements.md)
**Design:** [design.md](./design.md)

---

## Summary

This plan covers the backend face processing pipeline: asynchronous face detection and ArcFace embedding after photo upload, idempotent re-processing, retry on failure, AES-256-GCM embedding encryption, Qdrant-per-event vector storage, and the processing status endpoint. Testing ensures all six acceptance scenarios (async upload, multi-face indexing, zero-face handling, failure/retry, idempotency, and monitoring) are validated before the branch merges to main.

---

## Scope

**In scope:**
- `POST /api/v1/events/{event_id}/photos` upload endpoint
- `GET /api/v1/events/{event_id}/face-processing/status` monitoring endpoint
- `app/services/face_pipeline.py` — pipeline logic and idempotency gate
- `app/services/retry.py` — APScheduler stuck-job reset and failed-photo retry
- `app/utils/crypto.py` — AES-256-GCM encrypt/decrypt
- Photo and FaceRecord ORM model correctness
- Alembic migration 003 (structural check only)

**Explicitly out of scope:**
- Frontend dashboard UI (covered by Photographer Dashboard epic)
- Guest selfie search consuming embeddings (Face Recognition Search epic)
- Real InsightFace model download/inference (mocked in all automated tests)
- Real Qdrant Cloud connectivity (mocked in all automated tests)
- GPU acceleration (out of scope per requirements)
- HEIC/RAW file formats

---

## Requirements note: AC-1 / REQ-3 text vs implementation

AC-1 and REQ-3 state "a `face_records` entry with status `pending` exists … within the same request lifecycle." The implementation (per design.md) puts `processing_status` on the `photos` table, not `face_records`. `face_records` rows are only created after processing completes. The test plan validates the design intent: a `photos` row with `processing_status = 'pending'` exists after upload. This discrepancy should be reconciled in requirements.md.

---

## Test cases

### Happy path

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-01 | Upload returns 201 with pending status | POST a valid JPEG to `/api/v1/events/{id}/photos` with photographer JWT | HTTP 201; response body has `processing_status = "pending"` and a valid `photo_id` | **Missing** — needs implementation |
| TC-02 | Uploaded photo record is `pending` in DB | After TC-01, query `photos` table for the returned `photo_id` | `photos.processing_status = "pending"`, `file_size > 0`, `filename` set | **Missing** — needs implementation |
| TC-03 | Zero-face photo → complete, no face_records | Run pipeline with mocked InsightFace returning no faces | `photos.processing_status = "complete"`, `face_count = 0`, zero `face_records` rows | `test_run_pipeline_zero_faces` ✅ |
| TC-04 | Multi-face photo → correct face_records count | Run pipeline with 2 mocked faces | `face_count = 2`, 2 `face_records` rows, Qdrant upsert called once with 2 points | `test_run_pipeline_multiple_faces` ✅ |
| TC-05 | Multi-face photo → `complete` status | After TC-04 | `photos.processing_status = "complete"` | `test_run_pipeline_multiple_faces` ✅ |
| TC-06 | All face vectors upserted in single Qdrant call | Run pipeline with 3 mocked faces | `upsert_face_vectors` called exactly once with 3 points | **Missing** — TC-04 tests 2; add 3-face variant to match AC-2 exactly |
| TC-07 | Status endpoint returns correct per-status counts | Seed event with 7 complete / 2 pending / 1 failed; GET status | `total_photos = 10`, counts match exactly | **Missing** — current test uses 3 photos; needs 10-photo scenario with pending > 0 |
| TC-08 | Status endpoint: pending count > 0 included | Seed event with 1 pending photo; GET status | `by_status.pending = 1` | **Missing** — add to cover AC-6 pending count |

### Edge cases

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-10 | Sub-40px face is silently skipped | Run pipeline with a mocked face whose bounding box is 30×30 | No `face_records` row for that face; other faces (if any) still processed | **Missing** — REQ-4 not tested |
| TC-11 | Mix of valid and sub-40px faces in one photo | Run pipeline with mocked faces: one 100×100, one 20×20 | Exactly 1 `face_records` row; `face_count = 1` | **Missing** |
| TC-12 | Idempotency: re-run on `complete` photo | `process_photo` called on a photo already `complete` | `_run_pipeline` not called; no new `face_records` rows; existing records unchanged | `test_process_photo_skips_complete` ✅ |
| TC-13 | Idempotency: re-run on `processing` photo | `process_photo` called on a photo with status `processing` | `_run_pipeline` not called; no new rows | `test_process_photo_skips_in_processing` ✅ |
| TC-14 | Restart idempotency: stuck job reset then retried once | Photo stuck at `processing` for 20 min; APScheduler fires | Photo reset to `pending`; next `process_photo` call runs pipeline | `test_reset_stuck_jobs` ✅ (reset only); retry side missing — see TC-21 |
| TC-15 | Stuck job within threshold not reset | Photo in `processing` for 5 min; APScheduler fires | Photo remains `processing` | `test_reset_stuck_jobs_ignores_recent` ✅ |
| TC-16 | Zero-face photo not counted as failure in status | Seed event with one zero-face complete photo; GET status | `by_status.failed = 0`; `by_status.complete = 1` | **Missing** (covered by implication but not explicit) |
| TC-17 | Encryption: different ciphertexts for same embedding | Encrypt same `float32[512]` vector twice | Outputs differ (different nonces); each decrypts to original | `test_encrypt_produces_different_nonces` ✅ |
| TC-18 | Encryption: ciphertext length | Encrypt a `float32[512]` embedding | `len(ciphertext) == 2076` (12 nonce + 2048 payload + 16 tag) | `test_encrypt_produces_different_nonces` ✅ |
| TC-19 | Upload to non-owned event returns 404 | POST photo with user A's token to user B's event | HTTP 404 | **Missing** — inferred from `_get_owned_event` logic; needs explicit test |
| TC-20 | Upload with no token returns 401/403 | POST photo without Authorization header | HTTP 401 or 403 | **Missing** — needs explicit test |

### Failure / error paths

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-21 | InsightFace error → `failed` status | Mock `_detect_faces` to raise `RuntimeError`; `processing_attempts < 5` | `photos.processing_status = "failed"` | `test_run_pipeline_error_sets_failed` ✅ |
| TC-22 | Max-attempts exhausted → `error` status | Mock `_detect_faces` to raise; `processing_attempts = 5` | `photos.processing_status = "error"` | `test_run_pipeline_error_sets_error_at_max_attempts` ✅ |
| TC-23 | Qdrant write error → `failed` status, no partial vectors | Mock `upsert_face_vectors` to raise; `processing_attempts < 5` | `photos.processing_status = "failed"`; zero `face_records` rows; Qdrant upsert not partially committed | **Missing** — AC-4 partially covered (only InsightFace error tested) |
| TC-24 | `error` photos excluded from APScheduler retry | Seed a photo with `processing_status = "error"` and `processing_attempts = 5`; run `retry_failed_photos` | `process_photo` not called for that photo | **Missing** — `_retry_failed` function not tested at all |
| TC-25 | `failed` photo picked up by APScheduler | Seed a photo with `processing_status = "failed"` and `processing_attempts < 5`; run `retry_failed_photos` | `process_photo` called for that photo | **Missing** — AC-4b not tested |
| TC-26 | Error logging contains required fields | Trigger a pipeline failure | Log record contains `event_id`, `photo_id`, exception type | **Missing** — REQ-13 not tested |
| TC-27 | Status endpoint: no token → 401/403 | GET status without Authorization header | HTTP 401 or 403 | `test_status_endpoint_requires_auth` ✅ |
| TC-28 | Status endpoint: guest JWT → 403 | GET status with a valid guest-scoped JWT (not photographer) | HTTP 403 | **Missing** — AC-6b: current test only covers missing token; a guest JWT is a valid token that should be rejected differently |
| TC-29 | Status endpoint: wrong photographer → 404 | GET status with user A's JWT for user B's event | HTTP 404 | `test_status_endpoint_wrong_owner` ✅ |

---

## Acceptance criteria coverage

| Criterion | TC ID | Status |
|-----------|-------|--------|
| AC-1: Upload response returned before face detection; `photos` record has `processing_status = "pending"` | TC-01, TC-02 | **Not covered — TCs missing** |
| AC-1b: Face detection runs via InsightFace/ArcFace in background | TC-04 (mocked) | Partial — ArcFace model selection is manual only |
| AC-2: 3-face photo → exactly 3 face_records + 3 Qdrant points | TC-06 | **Not covered — needs 3-face variant** |
| AC-2b: Multi-face photo → `face_count = 3`, status `complete` | TC-04 *(2-face proxy)* | Partial — pattern covered, not exact count from AC |
| AC-3: Zero-face photo → `face_count = 0`, `complete`, zero face_records | TC-03 | ✅ Covered |
| AC-3b: Zero-face outcome — no error in upload response or status view | TC-03, TC-16 | Partial — TC-16 missing |
| AC-4: Qdrant write error → `failed`, logged, no partial vectors in Qdrant | TC-23 | **Not covered — TC-23 missing** |
| AC-4b: Failed photo retried by APScheduler without manual action | TC-25 | **Not covered — TC-25 missing** |
| AC-5: Already-complete photo re-run → no new records/vectors | TC-12 | ✅ Covered |
| AC-5b: Restart while `processing` → no duplicates after reset | TC-14, TC-15 | Partial — reset tested; full retry-after-reset cycle not end-to-end tested |
| AC-6: 10-photo event (7/2/1) → correct counts from status endpoint | TC-07, TC-08 | **Not covered — TCs missing** |
| AC-6b: Guest-scoped session → 403 | TC-28 | **Not covered — TC-28 missing** |
| AC-6c: Status reflects update within 5 seconds | — | Manual only (no caching in implementation) |

---

## Manual test checklist

These require real infrastructure or cannot be automated against mocks:

- [ ] **InsightFace model loads on cold start**: Start backend from scratch; confirm `INFO` log line indicating InsightFace loaded with ArcFace model; no crash or import error.
- [ ] **Upload is non-blocking**: Upload a large photo (~10 MB) and confirm the 201 response arrives before processing completes (check `processing_status = "pending"` at response time via status endpoint).
- [ ] **End-to-end pipeline on real image**: Upload a photo containing 2 known faces; wait for processing; confirm `face_count = 2` and 2 Qdrant vectors appear in the event's collection via Qdrant Cloud console.
- [ ] **Sub-40px face silently skipped in real image**: Upload a photo where one face is very small (crowd shot); confirm no error and only large faces appear in `face_records`.
- [ ] **APScheduler retry in production**: Simulate a failed photo (e.g. manually set `processing_status = "failed"`); wait 5 minutes; confirm APScheduler picks it up and either completes or increments `processing_attempts`.
- [ ] **ArcFace model selection**: Confirm via log or InsightFace `model_pack` setting that the ArcFace recognition model is active (not a different backbone).
- [ ] **CPU-only inference (NFR-1)**: Run pipeline on the 4-core VM; confirm no GPU usage (e.g. `nvidia-smi` shows 0%); confirm processing completes.
- [ ] **Qdrant collection isolation (NFR-3)**: Create two events; upload a photo to each; confirm via Qdrant Cloud that vectors for event A's collection are not visible in event B's collection query.
- [ ] **AC-6c staleness**: Transition a photo from `pending` to `complete` and poll the status endpoint; confirm the updated count appears within 5 seconds.
- [ ] **Failure logging format (REQ-13)**: Trigger a processing failure (e.g. corrupt image); confirm log line contains `event_id`, `photo_id`, exception class, and stack trace.

---

## Known risks

- **Atomicity of Qdrant + PostgreSQL (NFR-6)**: If Qdrant upsert succeeds but the subsequent PostgreSQL `face_records` INSERT fails, Qdrant holds orphaned vectors. These are harmless for correctness (they won't be returned without a matching `face_records` row), but they accumulate until event deletion. No automated test covers this partial-failure path — monitor Qdrant collection size vs. `face_records` count in production.
- **BackgroundTask loss on restart**: FastAPI `BackgroundTask` jobs are in-process. If the process crashes between HTTP response and task execution, the photo remains `pending` indefinitely — the APScheduler stuck-job reset only covers `processing`, not `pending`. Photos stuck at `pending` longer than expected would need a separate staleness monitor (not in scope for this epic).
- **InsightFace model download on first start**: If the model files are not pre-downloaded, the first processing call will download them (~500 MB). This blocks the first few jobs without failing them. Monitor `last_processed_at` lag on first deployment.
- **Guest JWT rejection (AC-6b)**: The status endpoint uses `get_current_user` (photographer JWT dependency). A guest JWT is structurally a valid JWT but with a different sub format. Whether it's rejected at the JWT decode step or the DB lookup step depends on implementation details — verify TC-28 manually if the guest token decoder and photographer decoder share the same `SECRET_KEY`.

---

## Sign-off

- [ ] All acceptance criteria covered (currently: 6 of 12 criteria have gaps — see TCs marked "Not covered" above)
- [ ] Missing TCs implemented and passing: TC-01, TC-02, TC-06, TC-07, TC-08, TC-16, TC-19, TC-20, TC-23, TC-24, TC-25, TC-26, TC-28
- [ ] Edge cases documented
- [ ] Manual checklist reviewed
- QA: — / —
