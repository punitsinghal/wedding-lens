## Epic
docs/epics/photographer-dashboard/EPIC.md

## Purpose
Give photographers a dedicated dashboard to upload photos directly to an event via drag-and-drop or folder selection, monitor face-processing progress in real time, and organise photos into albums — so they can deliver a guest-ready, fully indexed gallery with confidence that every photo has been processed before guests arrive.

## Scenarios in scope
1. Photographer uploads photos to an event (drag-and-drop or folder picker, JPEG/PNG, ≤ 25 MB, batch, triggers async face processing)
2. Upload resumes after a network interruption (chunked transfer, offset tracking, automatic resume)
3. Photographer monitors face-processing progress in real time (total / indexed / pending / failed counts, "Gallery ready" indicator)
4. Photographer manages albums (create, rename, delete — photos unassigned on delete; assign photos to one or more albums)
5. Photographer flags photos as "Photographer Choice" (toggle per photo, persisted, guest sessions cannot set)
6. Photographer is assigned to an event by the event owner (by email, scoped access, revocable)

## User stories / use cases
- As a photographer, I want to drag-and-drop or folder-select photos onto the dashboard, so that I can submit a large batch without clicking individual files.
- As a photographer, I want a failed upload to resume from where it left off, so that I don't lose progress on a slow or interrupted connection.
- As a photographer, I want a live progress view showing indexed vs pending photos, so that I know when the gallery is guest-ready.
- As a photographer, I want to create and organise albums within my event, so that guests can browse photos by ceremony.
- As a photographer, I want to flag my best shots as "Photographer Choice", so that guests see my curated picks prominently.
- As a bride/groom, I want to assign a photographer to my event by their email, so that they can upload and organise photos on my behalf.

## Functional requirements

### Scenario 1 — Photo upload
1. REQ-1 (Scenario 1): The upload UI must accept JPEG and PNG files via drag-and-drop onto a designated drop zone and via a folder/file picker.
2. REQ-2 (Scenario 1): The frontend must validate each file before upload begins — reject unsupported MIME types (anything other than JPEG/PNG) and files exceeding 25 MB — with an inline error per rejected file.
3. REQ-3 (Scenario 1): Each accepted file is transmitted to the backend, which stores it on the local SSD and records metadata (filename, size, event_id, album assignments) in PostgreSQL.
4. REQ-4 (Scenario 1): After each photo is stored, the backend must enqueue a `BackgroundTask` for face detection and embedding — the upload response must not wait for face processing to complete.
5. REQ-5 (Scenario 1): Uploading the same photo file (matched by content hash) to the same event a second time must be idempotent — no duplicate photo records created.

### Scenario 2 — Upload resume
6. REQ-6 (Scenario 2): Files must be uploaded in fixed-size chunks; chunk size and concurrency are design decisions.
7. REQ-7 (Scenario 2): The backend must persist received-chunk state per file so that a partial upload survives a client disconnect.
8. REQ-8 (Scenario 2): On reconnect, the client must query the backend for the last acknowledged chunk offset and resume from that point, skipping already-uploaded chunks.
9. REQ-9 (Scenario 2): A resumed upload must produce the same stored file as an uninterrupted upload — no corruption or partial records.

### Scenario 3 — Processing progress
10. REQ-10 (Scenario 3): The dashboard must display per-event photo counts: total uploaded, face-indexed (complete), pending (queued or in-progress), and failed.
11. REQ-11 (Scenario 3): Counts must refresh without a full page reload; whether this uses polling or push (SSE/WebSocket) is a design decision.
12. REQ-12 (Scenario 3): When all uploaded photos have been successfully face-indexed, the dashboard must display a clear "Gallery ready" indicator.
13. REQ-13 (Scenario 3): Failed face-processing jobs must appear with a count and a per-photo retry action available to the photographer.

### Scenario 4 — Album management
14. REQ-14 (Scenario 4): Photographers must be able to create albums with a name and an optional ceremony category tag (Ceremony, Sangeet, Mehendi, Haldi, Reception, Family Photos — same set as Event Management).
15. REQ-15 (Scenario 4): Photographers must be able to rename an existing album.
16. REQ-16 (Scenario 4): Photographers must be able to delete an album; deleting an album unassigns all its photos — the photos remain in the event and are not deleted.
17. REQ-17 (Scenario 4): Photographers must be able to assign photos to one or more albums; a single photo may belong to multiple albums simultaneously.

### Scenario 5 — Photographer Choice flag
18. REQ-18 (Scenario 5): Photographers must be able to toggle a "Photographer Choice" flag on any photo within their assigned event.
19. REQ-19 (Scenario 5): The flag state must be persisted in PostgreSQL against the photo record.
20. REQ-20 (Scenario 5): Only photographers assigned to the event (or the event owner) may set or clear the flag — a guest-scoped session must receive a 403 if it attempts to do so.

### Scenario 6 — Photographer assignment
21. REQ-21 (Scenario 6): The event owner must be able to assign a photographer to their event by entering the photographer's registered email address.
22. REQ-22 (Scenario 6): A photographer must only be able to view, upload to, and manage albums for events they have been explicitly assigned to.
23. REQ-23 (Scenario 6): The photographer dashboard landing page must list all events the photographer is currently assigned to.
24. REQ-24 (Scenario 6): The event owner must be able to remove a photographer's assignment, immediately revoking their access to that event's dashboard and upload endpoints.

## Non-functional requirements
- Upload of 1,000 photos must complete without manual retry on a stable connection.
- Dashboard progress counts must update within 5 seconds of a photo being face-indexed.
- A photographer must be able to complete upload and album organisation for a 500-photo event in under 30 minutes.
- Maximum file size: 25 MB per photo.
- Supported formats: JPEG and PNG only.

## Context
- Photographer authentication is email + password with JWT (ADR: `docs/decisions/2026-06-19-photographer-auth-email-password.md`). Photographer account registration and password reset are out of scope for this feature.
- Face processing runs as a FastAPI `BackgroundTask` — upload must never block on it (architecture constraint).
- Photos are stored on local SSD via the backend; the frontend never writes to storage directly (architecture constraint).
- This feature does not include Google Drive or Google Photos sync — that is deferred to the Photo Source Integration epic.

## Out of scope
- Google Drive and Google Photos sync (deferred to Photo Source Integration epic)
- Guest-facing gallery display (Album & Gallery Browsing epic)
- Photographer account registration and password reset (Auth feature)
- Per-event photo storage quotas (Admin Platform epic)
- HEIC and RAW file format support

## Open questions
- [ ] OQ-D1: What is the upload chunk size and concurrency strategy? — owner: Engineering
- [ ] OQ-D2: Is progress monitoring implemented via polling or server-sent events/WebSocket? — owner: Engineering
- [ ] OQ-D3: How is chunked upload state persisted (DB table, Redis, file)? — owner: Engineering
- [ ] OQ-D4: What is the database schema for photographer-event assignment? — owner: Engineering

## Acceptance criteria
- AC-1 (Scenario 1): A photographer drags a folder of 100 JPEG/PNG files (each ≤ 25 MB) onto the drop zone; all 100 are uploaded, stored on the SSD, and metadata recorded in PostgreSQL.
- AC-1b (Scenario 1): Uploading a file with an unsupported MIME type (e.g. HEIC, PDF) shows an inline error; the file is not transmitted to the backend.
- AC-1c (Scenario 1): Uploading a file exceeding 25 MB shows an inline size error; the file is not transmitted.
- AC-1d (Scenario 1): Uploading the same photo twice to the same event produces exactly one photo record.
- AC-2 (Scenario 2): With the connection cut after 20 of 50 files are fully received, re-triggering upload transmits only the remaining files — already-uploaded chunks are not re-sent.
- AC-3 (Scenario 3): The progress dashboard shows updated counts within 5 seconds of the backend marking a photo as face-indexed.
- AC-3b (Scenario 3): When all photos are indexed, the dashboard displays a "Gallery ready" indicator.
- AC-3c (Scenario 3): A failed face-processing job appears in the dashboard with a retry action.
- AC-4 (Scenario 4): A photographer creates an album named "Sangeet" with the Sangeet category tag; the album appears in the event's album list.
- AC-4b (Scenario 4): Deleting an album removes it from the album list; all previously assigned photos remain accessible in the event.
- AC-4c (Scenario 4): A photo assigned to two albums simultaneously appears in both album views.
- AC-5 (Scenario 5): A photographer toggles the Photographer Choice flag on a photo; the flag state persists across page reloads.
- AC-5b (Scenario 5): A guest-scoped session receives a 403 when attempting to set the Photographer Choice flag via the API.
- AC-6 (Scenario 6): An event owner assigns a photographer by email; the photographer logs in and sees the event on their dashboard.
- AC-6b (Scenario 6): After the event owner removes the photographer's assignment, the photographer can no longer access the event dashboard or upload photos to it.
- AC-6c (Scenario 6): A photographer cannot access the upload or album management pages for an event they have not been assigned to.

## Status
Groomed — ready for /design
