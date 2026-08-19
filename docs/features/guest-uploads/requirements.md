## Epic
(none — standalone feature; no parent epic exists for guest-contributed photos)

## Purpose
Let wedding guests contribute their own photos to the event gallery by scanning a QR code (e.g. on a table card or the invitation) and uploading directly from their phone's camera or gallery — no app install, no account, no sign-up — so that candid guest-taken moments the photographer never captures become part of the same searchable, shareable event gallery.

## Scenarios in scope
1. First-time guest upload (happy path) — guest scans the event QR code, lands on the gallery, taps an "Upload your photos" CTA, and submits photos with no app/account/sign-up.
2. Upload behind an access-gated event — for `access-code` / `magic-link-otp` events, the guest must pass the same access gate used for viewing the gallery before they can upload.
3. Batch upload in one session — guest selects/captures multiple photos and submits them together.
4. Guest-uploaded photos become searchable — uploaded photos enter the same face-processing pipeline as photographer uploads and appear in other guests' selfie search results.
5. Guest-uploaded photos appear in the shared gallery — processed guest photos are visible to all guests and the owner, no approval step.
6. Owner toggles guest uploads on/off — the event owner can enable/disable the capability per event.
7. Upload validation errors — a file with an unsupported format or over the size limit is rejected with a clear message; the rest of the batch continues.
8. Upload on an event with revoked guest access — upload attempts are blocked the same way viewing is blocked once the owner revokes guest access.

## User stories / use cases

### Scenario 1 — First-time guest upload
- As a wedding guest, I want to scan the event QR code and upload photos from my phone in one tap, so that I can share my own shots without installing an app or creating an account.

### Scenario 2 — Upload behind an access-gated event
- As a wedding guest at a private (access-code or OTP) event, I want the upload screen to respect the same access gate as the gallery, so that only invited guests can contribute photos.

### Scenario 3 — Batch upload
- As a wedding guest, I want to select several photos at once and upload them together, so that I don't have to repeat the upload flow for every single photo.

### Scenario 4 — Guest photos become searchable
- As a wedding guest, I want photos that other guests uploaded to be included when I search for myself, so that I don't miss photos of myself just because a guest, not the photographer, took them.

### Scenario 5 — Guest photos in the shared gallery
- As a wedding guest or the event owner, I want guest-uploaded photos to show up in the gallery as soon as they're processed, so that the gallery reflects everyone's contributions without waiting on manual approval.

### Scenario 6 — Owner toggles guest uploads
- As a bride/groom, I want to turn guest uploads off for my event if I don't want guest contributions, so that I retain control over what appears in my gallery.

### Scenario 7 — Upload validation errors
- As a wedding guest, I want to be told clearly if one of my photos can't be uploaded (wrong format, too large), so that I understand what happened and the rest of my batch still goes through.

### Scenario 8 — Revoked guest access
- As a bride/groom, I want guest uploads to stop working the moment I revoke guest access, so that no one can add photos to my gallery after the event access window closes.

## Functional requirements

### Scenario 1 — First-time guest upload
1. REQ-1 (Scenario 1): The event gallery must display a prominent "Upload your photos" call-to-action to any guest who has reached the gallery (i.e. passed the access gate, or immediately for public events).
2. REQ-2 (Scenario 1): Tapping the upload CTA must open the device's native camera/file picker, letting the guest take a new photo or choose existing ones — no app install, account, or sign-up required.
3. REQ-3 (Scenario 1): Before submitting, the guest may optionally enter a display name; if left blank, their uploaded photos are attributed as "Guest".
4. REQ-4 (Scenario 1): On submission, the guest must see a confirmation that their photo(s) were received and will appear in the gallery once processed.

### Scenario 2 — Upload behind an access-gated event
5. REQ-5 (Scenario 2): For events with `access_mode` of `access-code` or `magic-link-otp`, the upload CTA and upload screen must only be reachable with a valid guest session (the same gate used for gallery access).
6. REQ-6 (Scenario 2): For `public` events, no additional gate is required to reach the upload screen.
7. REQ-7 (Scenario 2): If a guest's session is missing or expired when they attempt to upload, they must be redirected to the access-code/OTP entry screen, consistent with existing gallery-access behavior.

### Scenario 3 — Batch upload in one session
8. REQ-8 (Scenario 3): A guest must be able to select or capture multiple photos and submit them as a single upload session.
9. REQ-9 (Scenario 3): A single guest upload session is capped at 20 photos; uploading more requires starting a new session.
10. REQ-10 (Scenario 3): Within a batch, valid files must upload successfully even if other files in the same batch are rejected (see Scenario 7).

### Scenario 4 — Guest-uploaded photos become searchable
11. REQ-11 (Scenario 4): Every guest-uploaded photo must be enqueued into the same face-processing pipeline (async, `BackgroundTask`) used for photographer uploads, scoped to the same `event_id`.
12. REQ-12 (Scenario 4): Once processed, guest-uploaded photos must be included in selfie search results for any guest of that event, with no distinction from photographer-uploaded photos in the search pipeline.
13. REQ-13 (Scenario 4): Guest upload submission must not block on face processing (architecture constraint: face processing is async).

### Scenario 5 — Guest-uploaded photos appear in the shared gallery
14. REQ-14 (Scenario 5): Once processed, a guest-uploaded photo must appear in the main event gallery grid alongside photographer-uploaded photos, with no owner approval step required.
15. REQ-15 (Scenario 5): A guest-uploaded photo must display a "Guest photo" indicator and the guest's display name (or "Guest" if none was given), distinguishing it from photographer-uploaded photos.
16. REQ-16 (Scenario 5): Guest-uploaded photos support the same guest-facing photo actions as photographer photos (view, favourite, download, share).
17. REQ-17 (Scenario 5): The event owner can assign a guest-uploaded photo to an album and mark it as Photographer's Choice, identically to a photographer-uploaded photo.

### Scenario 6 — Owner toggles guest uploads on/off
18. REQ-18 (Scenario 6): The event owner must be able to enable or disable guest uploads for their event, independent of `access_mode` or publish state.
19. REQ-19 (Scenario 6): Guest uploads default to **on** for newly created events.
20. REQ-20 (Scenario 6): When guest uploads are disabled, the "Upload your photos" CTA must not be shown, and any direct attempt to submit an upload must be rejected.

### Scenario 7 — Upload validation errors
21. REQ-21 (Scenario 7): Only `image/jpeg` and `image/png` content types are accepted, consistent with existing photo upload validation (`ALLOWED_CONTENT_TYPES` in photographer uploads).
22. REQ-22 (Scenario 7): Individual files exceeding 25 MB must be rejected, consistent with the existing `MAX_FILE_SIZE` limit used for photographer uploads.
23. REQ-23 (Scenario 7): A rejected file must show a clear, specific inline error (wrong format / too large) identifying which file failed, without discarding the rest of the batch — the guest must see per-file success/failure status.

### Scenario 8 — Upload on an event with revoked guest access
24. REQ-24 (Scenario 8): If the event owner has revoked guest access, upload attempts — including from a previously valid session — must be rejected with the same 401 behavior as gallery access, redirecting the guest to the access entry screen.

## Non-functional requirements
- NFR-1: Guest uploads remain scoped per `event_id` — a guest's uploaded photo must never be attributable to, or visible from, any other event (architecture constraint #3).
- NFR-2: Guest-uploaded photo files must be stored and processed through the same encryption-at-rest and face-embedding-encryption handling as photographer-uploaded photos (architecture constraint #2).
- NFR-3: No guest account or PII is stored beyond the optional free-text display name — consistent with the existing "no guest PII" decision in the Guest Access epic.
- NFR-4: Guest upload sessions should tolerate unreliable venue wifi without losing already-uploaded files in a batch — exact resilience strategy (resumable/chunked upload, retry behavior) is a design decision; prior art exists in the photographer upload flow (`docs/decisions/2026-06-21-chunked-upload-sse-frontend.md`, `docs/decisions/2026-06-19-chunked-upload-chunk-size-concurrency.md`).

## Context
- Reuses the existing Guest Access gate (`docs/epics/guest-access/EPIC.md`) — this feature adds an upload capability behind the same access check, it does not introduce a new access path or QR code.
- Guest-uploaded photos flow through the same photo storage, metadata, and face-processing path as photographer uploads (`docs/architecture/system.md`) — no new data store or pipeline is introduced.
- Photo action parity (REQ-16) builds on the existing Photo Actions feature (`docs/epics/photo-actions/EPIC.md`) for download/favourite/share.
- Album assignment and Photographer's Choice (REQ-17) build on existing photographer-dashboard photo-management actions described in `docs/features/product-ux/ux.md`.

## Out of scope
- Owner moderation/approval queue before a guest photo becomes visible — decided: immediate visibility, no moderation step.
- Guest editing or deleting their own uploaded photo after submission — only the event owner can remove a photo, via existing photo-management capability.
- A separate/dedicated QR code for uploads — this feature reuses the existing per-event gallery QR code plus a new in-gallery CTA; no second QR is generated or printed.
- Guest account creation or any authentication mechanism beyond the existing access-gate (code/OTP/public).
- Storage/dashboard analytics changes beyond what's needed to count guest photos alongside photographer photos (no new analytics dimension in this feature).

## Open questions
- [ ] What is the exact resilience/retry strategy for guest uploads on unreliable venue wifi (resumable chunked upload vs. simple retry-on-failure)? — owner: Engineering (design deferral, see NFR-4)
- [ ] Should there be a rate limit on upload sessions per guest/event to prevent abuse, and if so what threshold? — owner: Engineering (design deferral; existing code-entry rate limiting is prior art)
- [ ] Does a guest-uploaded photo count toward any per-event storage limit or quota, and does that change owner-facing storage analytics? — owner: Engineering

## Acceptance criteria
- AC-1 (Scenario 1): A guest scans the event QR code, reaches the gallery (directly for public events, after the access gate otherwise), taps "Upload your photos," picks a photo via the native picker, and submits without being asked to install anything or create an account; a confirmation message is shown.
- AC-2 (Scenario 2): For an `access-code` event, a guest without a valid session who taps the upload link is redirected to the code entry screen; after entering a valid code, they reach the upload screen.
- AC-2b (Scenario 2): For a `public` event, a guest reaches the upload screen with no code/OTP prompt.
- AC-3 (Scenario 3): A guest selects 5 photos in one picker interaction and submits; all 5 are received in a single upload session and confirmed together.
- AC-3b (Scenario 3): A guest attempts to select 25 photos in one session; the system caps the session at 20 and communicates the cap to the guest.
- AC-4 (Scenario 4): A guest uploads a photo containing another guest's face; once processing completes, that other guest's selfie search returns the guest-uploaded photo alongside any photographer-uploaded matches.
- AC-5 (Scenario 5): A processed guest-uploaded photo appears in the main gallery grid, tagged with a "Guest photo" indicator and the guest's display name (or "Guest" if blank), without any owner action required to publish it.
- AC-5b (Scenario 5): The event owner assigns a guest-uploaded photo to an album and marks it Photographer's Choice; both actions succeed and are reflected in the gallery, identically to a photographer-uploaded photo.
- AC-6 (Scenario 6): A newly created event has guest uploads enabled by default; the owner disables the toggle, and the "Upload your photos" CTA disappears from the gallery for all guests of that event.
- AC-6b (Scenario 6): With guest uploads disabled, a direct upload submission (bypassing the UI) is rejected by the backend.
- AC-7 (Scenario 7): A guest selects one valid JPEG and one 30 MB file in the same batch; the JPEG uploads successfully, the oversized file is rejected with a specific "file too large" message identifying that file, and the batch overall is reported as partially successful.
- AC-7b (Scenario 7): A guest selects a `.heic` file; it is rejected with a specific "unsupported format" message.
- AC-8 (Scenario 8): After the event owner revokes guest access, a guest with a previously valid session attempts to upload; the request is rejected with 401 and the guest is redirected to the access entry screen, matching existing gallery-access revocation behavior.

## Status
Groomed — ready for /design
