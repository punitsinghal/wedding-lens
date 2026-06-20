## Epic
docs/epics/face-recognition-search/EPIC.md

## Purpose
Allow wedding guests to upload a selfie and instantly receive a list of all photos from their event in which they appear, eliminating the need to manually browse thousands of images. The feature covers the full selfie-to-results flow — from upload through face extraction, vector search, and result delivery — within a single guest session.

## Scenarios in scope
1. Guest uploads a selfie with a clear single face — matching photos returned in under 5 seconds
2. Guest uploads a selfie where no face is detected — user-friendly error shown; no search is performed
3. Guest uploads a selfie containing multiple faces — system selects the face with highest detection confidence and proceeds; if no single dominant face exists, an error is shown asking the guest to upload a clearer selfie
4. Guest re-runs the search by uploading a new selfie — fresh search replaces previous results; stale results not visible during in-progress state
5. Guest uploads the same selfie again within the same session — cached results are returned instantly within a 1-hour cache window
6. Search results are strictly scoped to the guest's event — photos from other events are never returned
7. Selfie is deleted immediately after embedding is extracted — no selfie file persists beyond the extraction step, even if extraction fails

## User stories / use cases

### Scenario 1 — Single clear selfie
- As a guest, I want to upload a selfie so that I can instantly see all event photos where I appear, without browsing the full gallery.

### Scenario 2 — No face detected
- As a guest, I want a clear explanation when my selfie cannot be used, so that I understand what went wrong and can try again with a better photo.

### Scenario 3 — Multiple faces in selfie
- As a guest, I want the system to still work if other people appear in my selfie, so that I don't have to re-take the photo if someone is partially in the frame.
- As a guest, I want a clear message when the system cannot determine which face to use, so that I know to upload a selfie with just my face.

### Scenario 4 — Re-run search
- As a guest, I want to upload a different selfie and start a fresh search, so that I can try a better photo if my results are unsatisfactory.

### Scenario 5 — Cached results
- As a guest, I want repeated uploads of the same selfie to return results immediately, so that I am not forced to wait again for an identical search.

### Scenario 6 — Event isolation
- As a system, I want searches to be scoped to the guest's event, so that a guest at one wedding can never receive photos from another event.

### Scenario 7 — Selfie deletion
- As a guest, I want my uploaded selfie deleted as soon as it has been processed, so that my biometric data is not retained beyond what is strictly necessary.

## Functional requirements

### Scenario 1 — Single clear selfie
1. REQ-1 (Scenario 1): The frontend must provide a selfie upload control that accepts JPEG and PNG files via file picker and, where supported by the browser, via camera capture.
2. REQ-2 (Scenario 1): On submission, the frontend must POST the selfie to the backend search endpoint; the frontend must not perform face extraction or search directly against any data store.
3. REQ-3 (Scenario 1): The backend must extract a face embedding from the selfie using InsightFace (ArcFace model) and perform a vector similarity search against all face embeddings indexed for the guest's event in Qdrant.
4. REQ-4 (Scenario 1): The search must return only results with a similarity score of ≥ 0.4, capped at the top 50 matches ordered by descending similarity score. One result is returned per photo (not per face detection); if multiple matched faces belong to the same photo, the highest similarity score for that photo is used for ranking.
5. REQ-5 (Scenario 1): The end-to-end selfie-to-results flow must complete within 5 seconds at p95.
6. REQ-6 (Scenario 1): The response payload must include, for each matched photo: photo ID and thumbnail URL. Similarity scores must not be exposed to the frontend.
7. REQ-7 (Scenario 1): The frontend must display results as one card per photo, in ranked order (highest match first). No score or confidence indicator is shown to the guest.

### Scenario 2 — No face detected
8. REQ-8 (Scenario 2): If the backend's face detector finds no face in the uploaded selfie, the search must not be performed and the backend must return a structured error response.
9. REQ-9 (Scenario 2): The frontend must display a user-friendly message when no face is detected, explaining what the problem is and prompting the guest to upload a clearer selfie. The raw error code must not be shown.

### Scenario 3 — Multiple faces in selfie
10. REQ-10 (Scenario 3): If the backend detects more than one face in the selfie, it must select the face with the highest detection confidence score and proceed with that embedding.
11. REQ-11 (Scenario 3): If all detected faces have confidence scores within 10 percentage points of each other (no single dominant face), the backend must return a structured error; no search is performed.
12. REQ-12 (Scenario 3): When the no-dominant-face error is returned, the frontend must display a message asking the guest to upload a selfie that shows only their face.

### Scenario 4 — Re-run search
13. REQ-13 (Scenario 4): A guest must be able to initiate a new search at any time by uploading a different selfie; each upload triggers a fully independent search.
14. REQ-14 (Scenario 4): On a new upload, previously displayed results must be replaced by the results of the new search. Stale results must not remain visible during the in-progress state.

### Scenario 5 — Cached results
15. REQ-15 (Scenario 5): The backend must compute a hash of the raw uploaded bytes for each selfie request and check whether a result set for that hash already exists in the guest's session cache.
16. REQ-16 (Scenario 5): If a valid cached result set exists (same hash, same session, within 1 hour of original search), the backend must return the cached result set without re-running face extraction or vector search.
17. REQ-17 (Scenario 5): The cache is scoped to the guest's session token; a different guest uploading the same selfie bytes must not receive another guest's cached results.

### Scenario 6 — Event isolation
18. REQ-18 (Scenario 6): The backend must extract the `event_id` from the guest's session token and apply it as a mandatory filter on every Qdrant search request; the `event_id` provided by the client in the request body (if any) must be ignored.
19. REQ-19 (Scenario 6): The backend must validate the session token's `event_id` on every search request before any face extraction or search is attempted; requests with an invalid or missing session token must be rejected with a 401.

### Scenario 7 — Selfie deletion
20. REQ-20 (Scenario 7): The selfie file must be deleted from all temporary storage as soon as the face embedding has been extracted, before the vector search begins. The selfie must not be written to persistent storage at any point.
21. REQ-21 (Scenario 7): Selfie deletion must occur even if the embedding extraction fails or returns an error — no selfie bytes may remain in any writable location after the request is processed.

## Non-functional requirements
- NFR-1: Selfie-to-results latency must be under 5 seconds at p95 under normal single-VM load.
- NFR-2: Zero selfie files may persist after a request completes, whether the request succeeds or fails.
- NFR-3: All face embeddings stored in Qdrant must be encrypted at rest (architecture-wide constraint).
- NFR-4: Cross-event data leakage must be architecturally impossible — the `event_id` scope must be enforced in the backend, not by client-provided parameters.
- NFR-5: The selfie upload endpoint must enforce a maximum file size of 20 MB; requests exceeding this limit must be rejected before any processing occurs.
- NFR-6: The similarity threshold (0.4) and result cap (50) must be deployment-level configuration values, not hardcoded, so they can be adjusted without a code change.

## Context
- Guest access is anonymous — no user accounts. Guests authenticate via a session token issued after QR code entry (and optional PIN). The session token carries the `event_id` and is the sole source of event scoping for search requests.
- The frontend calls the backend REST API only; it never queries Qdrant or PostgreSQL directly (architecture constraint).
- Face embeddings in Qdrant are 512-dimensional ArcFace vectors, generated during photo indexing by the photographer-upload pipeline. Search results reference photo IDs stored in PostgreSQL.
- Photo download and ZIP generation from the results page are handled by the Photo Actions epic and are not part of this feature's delivery.
- Result caching is session-scoped, not global — the same selfie bytes from two different guest sessions produce two independent cache entries.
- The similarity threshold (0.4) and result cap (50) are decisions taken by Engineering and Product Team respectively; the threshold tuning UI is out of scope.
- Similarity scores are an internal implementation detail — they are used for ranking and filtering but must not be surfaced to guests in any form (no percentages, stars, or labels).
- Results are deduplicated per photo before being returned; if a photo contains multiple matched faces, the photo appears once using its highest similarity score for ranking.

## Out of scope
- Photo download, share, and ZIP download from the results page (Photo Actions epic)
- Photo browsing and gallery display (Album & Gallery Browsing epic)
- Similarity threshold tuning UI — threshold is deployment-level config, not per-event or per-guest
- Face recognition search for photographers or event owners (guests only in this feature)
- Offline or low-connectivity handling beyond a standard HTTP timeout
- Displaying similarity scores or confidence indicators to guests

## Open questions
<!-- All functional gaps resolved during grooming on 2026-06-20. No open questions remain. -->

## Acceptance criteria
- AC-1 (Scenario 1): A guest uploads a JPEG selfie showing a single clear face; within 5 seconds the results page displays one card per photo for all event photos where that face appears (similarity ≥ 0.4), ordered by descending match rank, with at most 50 results. No score or confidence indicator is shown.
- AC-1b (Scenario 1): If no event photos match at or above the threshold, the results page shows a "no photos found" state rather than an error.
- AC-2 (Scenario 2): A guest uploads an image containing no detectable face (e.g. a landscape photo); the search is not executed and the frontend displays a user-friendly message instructing the guest to upload a selfie that clearly shows their face.
- AC-3 (Scenario 3): A guest uploads a selfie where one face has a detection confidence score at least 10 percentage points higher than all others; the system runs the search using that face and returns results normally.
- AC-3b (Scenario 3): A guest uploads a selfie where two or more faces have confidence scores within 10 percentage points of each other; the search is not executed and the frontend displays a message asking the guest to upload a selfie showing only their face.
- AC-4 (Scenario 4): A guest uploads a first selfie and sees results. They then upload a second, different selfie; the results area updates to show only the results for the second selfie, with no results from the first search remaining visible.
- AC-5 (Scenario 5): A guest uploads a selfie, receives results, then uploads the same selfie bytes again within 1 hour and the same session; the second response is served from cache without re-running face extraction or vector search (verifiable via backend logs or a response header indicating cache hit).
- AC-5b (Scenario 5): A guest uploads the same selfie bytes more than 1 hour after the original search within the same session; the cache is not used and a fresh search is performed.
- AC-6 (Scenario 6): A guest session scoped to Event A uploads a selfie; the response contains only photos belonging to Event A — no photo from Event B or any other event appears in the results.
- AC-6b (Scenario 6): A request to the search endpoint that carries an invalid or expired session token receives a 401 response; no face extraction or search is performed.
- AC-7 (Scenario 7): After a successful search request, no selfie file exists in any temporary or writable directory on the server — confirmed by the absence of any selfie bytes in storage after the response is returned.
- AC-7b (Scenario 7): If face extraction fails (e.g. model error), the selfie is still deleted before the error response is returned; no selfie bytes remain on disk.

## Status
Groomed — ready for /design
