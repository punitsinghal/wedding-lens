# ADR: Guest Photo Uploads Sent as Independent Per-File Requests
Date: 2026-08-19
Status: accepted

## Context

The Guest Uploads feature (`docs/features/guest-uploads/requirements.md`) lets a wedding guest upload up to 20 photos from their phone in one session, over venue wifi that may be slow or unreliable — this resilience question was explicitly flagged as an open design question during grooming (NFR-4).

Three ways exist to get a guest's batch of photos to the backend, and the codebase already has prior art for two of them: `routers/photos.py` uses a simple one-file-per-request multipart upload for photographer manual uploads, and `routers/uploads.py` implements a full chunked/resumable session protocol (initiate → chunk → complete, with content-hash dedup) for the photographer's bulk-upload dashboard.

## Decision

Guest uploads are sent as **N independent per-file `POST` requests** — one `multipart/form-data` request per photo, not a single request carrying all files, and not a reuse of the photographer's chunked/resumable session infrastructure.

The frontend loops over the guest's selected photos, issuing 2–3 concurrent requests (matching the existing photographer-upload concurrency convention), each authenticated with the guest's JWT via the existing `get_validated_guest_event` dependency. A per-`(event_id, sid)` in-process counter (new, small — mirrors the existing `rate_limiter` pattern in `guest_auth.py`) enforces the 20-photos-per-session cap and doubles as a cheap abuse-prevention ceiling.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| A — Single batch multipart request (all files in one POST) | Simplest server-side code; the 20-file cap is a trivial `len(files) > 20` check | All-or-nothing failure: a dropped connection mid-transfer loses every file in the batch, including ones already fully sent; request bodies up to ~500MB (20 × 25MB) risk proxy/reverse-proxy timeout on the single-VM deployment |
| B — N independent per-file requests (chosen) | A dropped connection only costs the one file in flight; already-uploaded files in the same guest session stand; each request body is capped at 25MB, well within any reasonable proxy timeout; reuses the existing single-file validation constants from `photos.py` as-is | The "batch" is a client-side/counter convention rather than a single atomic operation; needs a small new per-session counter to enforce the 20-file cap server-side (in-process state, not persisted) |
| C — Reuse the photographer's chunked/resumable upload session (`uploads.py`) | Maximum resilience: per-chunk retry and resume, existing content-hash dedup | Built for a different problem (photographer bulk-uploading potentially thousands of photos) and a different auth model (photographer JWT via `get_event_with_photographer_access`); adapting the session/chunk/dedup machinery to guest auth and single phone-camera photos is significant rework for resilience the simpler Option B already provides at this file-size scale |

## Consequences

- Easier: implementation stays small — the new endpoint reuses existing content-type/size constants and the existing guest-auth dependency verbatim; per-file failure handling is free (each request is independently pass/fail, satisfying REQ-10's "one bad file doesn't block the rest of the batch" without any batch-transaction logic).
- Harder: the guest-facing "batch" experience (progress across N files, one confirmation message) is entirely a frontend concern — the backend has no concept of a "session" beyond the per-`(event_id, sid)` counter used for the cap.
- Follow-on: the per-session counter introduced here is deliberately generic enough to serve as the mechanism for a future abuse-rate-limit threshold (left as a build-time constant, not fixed by this ADR) — see the design doc's open questions.

## References
- `docs/features/guest-uploads/requirements.md` (REQ-8, REQ-9, REQ-10, NFR-4)
- `docs/features/guest-uploads/design.md`
- Prior art: `backend/app/routers/photos.py` (single-file upload, content-type/size constants), `backend/app/routers/uploads.py` (chunked/resumable session, rejected as Option C), `backend/app/services/guest_auth.py` (`rate_limiter` pattern reused for the per-session counter)
