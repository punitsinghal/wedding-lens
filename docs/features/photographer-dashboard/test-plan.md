## Summary

This test plan covers the photographer dashboard feature: batch photo upload (drag-and-drop and folder picker), chunked-upload resume after network interruption, real-time face-processing progress monitoring, album management, the Photographer Choice flag, and photographer-to-event assignment. This feature is the primary data ingestion path for the platform — correctness here determines whether the guest gallery is complete and whether every photo has been face-indexed before guests arrive.

---

## Scope

**In scope:**
- Photo upload via drag-and-drop and folder/file picker (JPEG/PNG, ≤ 25 MB)
- Frontend file validation (MIME type, file size) before transmission
- Backend storage (SSD) and metadata recording (PostgreSQL)
- Async face-processing enqueue — upload must not block on it
- Idempotent duplicate upload (content-hash deduplication)
- Chunked upload and resume after disconnect
- Processing progress dashboard (total / indexed / pending / failed counts, "Gallery ready" indicator)
- Per-photo retry for failed face-processing jobs
- Album management (create, rename, delete, multi-album photo assignment)
- Photographer Choice flag (toggle, persist, guest 403 enforcement)
- Photographer assignment by email (scoped access, revocation)

**Out of scope:**
- Google Drive / Google Photos sync — deferred to Photo Source Integration epic
- Guest-facing gallery and album browsing — Album & Gallery Browsing epic
- Photographer account registration and password reset — Auth feature
- Per-event photo storage quotas — Admin Platform epic
- HEIC and RAW file format support
- Face detection and embedding implementation — AI Face Processing epic

---

## Open design questions blocking test design

The following questions from the requirements are unresolved. Test cases that depend on them are marked **⚠ blocked** until Engineering decides.

| OQ | Question | TC affected |
|----|----------|-------------|
| OQ-D1 | Upload chunk size and concurrency strategy | TC-12, TC-13, TC-14 |
| OQ-D2 | Progress monitoring: polling interval vs SSE/WebSocket | TC-20, TC-21 |
| OQ-D3 | Chunked upload state persistence: DB table, Redis, or file | TC-12, TC-13, TC-14 |
| OQ-D4 | Database schema for photographer-event assignment | TC-30, TC-31 |

---

## Assumptions

| # | Assumption | TC affected |
|---|------------|-------------|
| A1 | ✅ Confirmed: Upload resumes automatically on reconnect — no manual photographer action required | TC-13, TC-23 |
| A2 | ✅ Confirmed: Content-hash computed client-side before upload, sent as request header; backend uses it for duplicate detection | TC-06, TC-11 |
| A3 | SSD storage verification in automated tests uses a backend endpoint (e.g. `GET /api/v1/admin/photos/{id}/storage-check`) or direct filesystem access in the test environment | TC-02, TC-03 |
| A4 | The 1,000-photo endurance test (NFR) is a long-running automated integration test, not a manual test | TC-16 |
| A5 | ✅ Confirmed: "Under 30 minutes for 500-photo event" (NFR) is a manual UX timing check — not automated | M-05 |

---

## Test cases

### Happy path

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-01 | Upload via drag-and-drop — files stored and metadata recorded | Drag 5 JPEG files onto drop zone; check backend | 200 per file; each photo record in PostgreSQL with filename, size, event_id; files present on SSD (A3) | Yes |
| TC-02 | Upload via folder picker — same result as drag-and-drop | Open folder picker; select folder of 5 PNGs; submit | Same as TC-01 | Yes |
| TC-03 | Upload response returns before face processing completes | Upload 1 photo; record upload response timestamp; record face-processing completion timestamp | Upload response time < face-processing completion time; upload is not blocked | Yes |
| TC-04 | Face-processing BackgroundTask enqueued per photo | Upload 1 photo; inspect task queue or DB job table | One face-processing job record created for the photo; status is `pending` or `queued` | Yes |
| TC-05 | Batch upload of 100 photos completes (AC-1) | Upload a mixed JPEG/PNG batch of 100 files (each ≤ 25 MB) | All 100 photo records in PostgreSQL; all 100 files on SSD; 100 face-processing jobs enqueued | Yes |
| TC-06 | Duplicate upload is idempotent (AC-1d, A2) | Upload same file twice to same event | Exactly one photo record in PostgreSQL; second upload returns 200 with the existing record ID (no new record) | Yes |
| TC-07 | Create album with category tag (AC-4) | POST album with name="Sangeet", tag=`Sangeet` | 201; album appears in event album list with correct name and tag | Yes |
| TC-08 | Rename album | PATCH album with new name | 200; album name updated; photos and tag unchanged | Yes |
| TC-09 | Delete album — photos unassigned, not deleted (AC-4b) | Assign 3 photos to album; delete album | Album removed; 3 photos still in event with `album_id = null` | Yes |
| TC-10 | Assign photo to multiple albums simultaneously (AC-4c) | Assign 1 photo to album A and album B | Photo appears in both album A and album B views | Yes |
| TC-11 | Toggle Photographer Choice flag — persists (AC-5) | Toggle flag on; reload page; check flag state | Flag is `true` in database; flag state visible after reload | Yes |
| TC-12 | Toggle Photographer Choice flag off — persists | Toggle flag on; toggle flag off; reload page | Flag is `false` in database | Yes |
| TC-13 | Owner assigns photographer by email — event appears on photographer dashboard (AC-6) | Owner assigns photographer@example.com to event; photographer logs in | Event appears in photographer's dashboard event list | Yes |
| TC-14 | Photographer can upload to assigned event | Photographer assigned to event; POST photo upload | 200; photo stored in event | Yes |
| TC-15 | Progress counts update within 5 seconds of indexing (AC-3) | Upload 1 photo; wait for face-indexing job to complete; poll or subscribe to progress endpoint | Dashboard counts reflect `indexed+1` within 5 seconds of job completion | Yes |
| TC-16 | "Gallery ready" indicator shows when all photos indexed (AC-3b) | Upload 3 photos; wait for all 3 to be face-indexed | Dashboard displays "Gallery ready" indicator; `pending` count is 0 | Yes |
| TC-17 | Failed face-processing job appears with retry action (AC-3c) | Trigger a face-processing failure (e.g. corrupt image); check dashboard | Failed job count increments; retry action available per failed photo | Yes |
| TC-18 | Retry action re-enqueues failed face-processing job | Click retry on failed job | New face-processing job enqueued for that photo; status changes from `failed` to `pending` | Yes |

---

### Edge cases

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-19 | Unsupported MIME type rejected client-side (AC-1b) | Drag a `.heic` file onto the drop zone | Inline error shown for that file; no HTTP request sent to backend for that file | No (manual — requires browser inspection) |
| TC-19b | Unsupported MIME type also rejected server-side | POST upload request with `Content-Type: image/heic` | 422 from backend; file not stored | Yes |
| TC-20 | File exceeding 25 MB rejected client-side (AC-1c) | Drag a 30 MB JPEG onto the drop zone | Inline size error shown; no upload request sent | No (manual — requires browser inspection) |
| TC-20b | File exceeding 25 MB also rejected server-side | POST 30 MB payload to upload endpoint | 413 or 422 from backend; file not stored | Yes |
| TC-21 | Progress counts refresh without full page reload (REQ-11) | Upload a photo; observe dashboard counts update | Count increments without browser navigation or full-page HTML reload | No (manual) |
| TC-22 | 1,000-photo endurance upload — no manual retry (NFR, A4) | Upload 1,000 photos in a single session on a stable connection | All 1,000 records in PostgreSQL; no upload failure requiring manual retry | Yes (long-running) |
| TC-23 | Chunked upload — resume transmits only remaining chunks (AC-2, ⚠ OQ-D1/D3) | Start uploading a large file; cut network after chunk N; reconnect; observe resumed upload | Only chunks after N are re-transmitted; no duplicate chunk data stored | Yes — blocked on OQ-D1 and OQ-D3 |
| TC-24 | Resumed upload produces identical file (REQ-9, ⚠ OQ-D1/D3) | Complete TC-23 resume scenario; compare SHA-256 of stored file to original | Hashes match; no corruption | Yes — blocked on OQ-D1 and OQ-D3 |
| TC-25 | Photographer assigned to event cannot access another event | Photographer assigned to event A; GET upload endpoint for event B | 403 | Yes |
| TC-26 | Photographer with no assignments sees empty dashboard (REQ-23) | Photographer logs in with no event assignments | Dashboard shows empty event list; no events accessible | Yes |
| TC-27 | Progress counts: pending decrements as jobs complete | Upload 3 photos; observe pending count over time | Pending starts at 3; decrements to 0 as each job completes | Yes |

---

### Failure / error paths

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-28 | Unauthenticated upload request → 401 | POST to upload endpoint with no `Authorization` header | 401 | Yes |
| TC-29 | Authenticated owner cannot upload to another owner's event | Authenticated as owner-B; POST upload to event owned by owner-A | 403 | Yes |
| TC-30 | Guest session receives 403 on Photographer Choice flag (AC-5b) | POST flag toggle with a guest-scoped JWT | 403 | Yes |
| TC-31 | Photographer cannot access unassigned event dashboard (AC-6c) | Authenticated as photographer; GET dashboard for unassigned event | 403 | Yes |
| TC-32 | Owner revokes photographer assignment — access immediately blocked (AC-6b) | Owner removes photographer; photographer GETs event dashboard | 403 | Yes |
| TC-33 | Revoked photographer cannot upload to event | Owner removes photographer; photographer POSTs upload | 403; file not stored | Yes |
| TC-34 | Upload endpoint rejects non-JPEG/PNG at server level | POST with `Content-Type: application/pdf` | 422; file rejected | Yes |
| TC-35 | Mixed batch — valid files upload, invalid files produce per-file errors | Drag batch containing 3 valid JPEGs and 1 HEIC; submit | 3 photos uploaded successfully; 1 inline error shown for HEIC; no request sent for HEIC | No (manual) |

---

## Acceptance criteria coverage

| Criterion | TC IDs | Status |
|-----------|--------|--------|
| AC-1: 100 JPEG/PNG files uploaded, stored, metadata recorded | TC-05 | Covered |
| AC-1b: Unsupported MIME type shows inline error, not transmitted | TC-19, TC-19b | Covered (TC-19 manual) |
| AC-1c: File > 25 MB shows inline size error, not transmitted | TC-20, TC-20b | Covered (TC-20 manual) |
| AC-1d: Duplicate upload produces exactly one record | TC-06 | Covered |
| AC-2: Resume transmits only remaining chunks after disconnect | TC-23 | Covered — ⚠ blocked on OQ-D1/D3 |
| AC-3: Progress counts update within 5 seconds of indexing | TC-15 | Covered |
| AC-3b: "Gallery ready" indicator when all indexed | TC-16 | Covered |
| AC-3c: Failed job shows with retry action | TC-17, TC-18 | Covered |
| AC-4: Album created with name and category tag | TC-07 | Covered |
| AC-4b: Deleting album keeps photos in event | TC-09 | Covered |
| AC-4c: Photo in two albums appears in both | TC-10 | Covered |
| AC-5: Photographer Choice flag persists across reloads | TC-11 | Covered |
| AC-5b: Guest 403 on Photographer Choice flag | TC-30 | Covered |
| AC-6: Owner assigns photographer; photographer sees event | TC-13 | Covered |
| AC-6b: Owner removes assignment; photographer loses access | TC-32, TC-33 | Covered |
| AC-6c: Photographer cannot access unassigned event | TC-31 | Covered |

**Blocked criteria:**
- AC-2 depends on OQ-D1 (chunk size) and OQ-D3 (state persistence) — TC-23 cannot be finalised until these are resolved.

---

## Manual test checklist

- [ ] **M-01 (AC-1b):** Drag a `.heic` file and a `.pdf` file onto the drop zone in a real browser — confirm per-file inline errors appear and the browser network tab shows no upload request for those files.
- [ ] **M-02 (AC-1c):** Drag a file larger than 25 MB — confirm an inline size error appears and no upload request is sent.
- [ ] **M-03 (REQ-11):** Upload a photo; watch the dashboard progress counts — confirm counts increment without a full page reload or URL change.
- [ ] **M-04 (TC-35):** Drag a mixed batch (valid + invalid files) — confirm valid files upload and invalid files show per-file errors with no mixing of results.
- [ ] **M-05 (NFR):** Time the full upload and album-organisation workflow for a 500-photo event. Confirm it completes within 30 minutes on a stable connection.
- [ ] **M-06 (AC-3b):** After all photos in an event are face-indexed, confirm the "Gallery ready" indicator is visually prominent and clearly distinct from the progress view.
- [ ] **M-07 (AC-2):** During a large upload, disconnect the network at a visible progress point; reconnect; confirm upload resumes automatically from the correct offset — no manual re-trigger button required.

---

## Known risks

1. **Open design questions gate three scenarios:** TC-23 (upload resume), TC-24 (resume integrity), and indirectly TC-15/TC-21 (progress update mechanism) cannot be finalised until OQ-D1–D3 are resolved. If Engineering resolves these after test implementation begins, the test cases will need revision.

2. **AC-2 ambiguity — automatic vs manual resume (A1):** AC-2 says "re-triggering upload" which implies a photographer action, but REQ-8 says "on reconnect, the client must query...and resume" which implies automatic. If the implementation requires a manual re-trigger button, M-07 must be updated and TC-23 rewritten.

3. **Content-hash deduplication client-side cost (A2):** SHA-256 of 1,000 photos client-side may block the UI thread on low-spec devices (wedding venue tablets, older phones). This is a performance risk not covered by automated tests — worth a manual check on representative hardware.

4. **5-second progress update SLA (AC-3):** This SLA applies regardless of whether progress uses polling or SSE. If polling, the interval must be ≤ 5 seconds. If SSE/WebSocket, the backend must emit the event within 5 seconds of the indexing job completing. Either way, TC-15 is sensitive to test environment load — a slow CI runner may cause false failures.

5. **Idempotency on concurrent duplicate uploads (TC-06):** The deduplication check (content-hash) may have a race window if two identical files are uploaded simultaneously. A concurrent-duplicate test should be added once OQ-D2/D3 are resolved.

6. **1,000-photo endurance test duration:** TC-22 may take 30+ minutes depending on chunk size and concurrency. It should be tagged as `@slow` and excluded from the default CI run — promoted to a nightly or pre-release suite.

---

## Sign-off

- [x] All acceptance criteria covered
- [x] Edge cases documented
- [x] Manual checklist reviewed
- QA: Punit Singhal — 2026-06-19
