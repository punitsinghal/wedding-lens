## Epic
docs/epics/photo-actions/EPIC.md

## Status
Groomed — ready for /design

## Purpose
Allow authenticated wedding guests to download individual or bulk sets of photos at original resolution, generate event-scoped shareable links to specific photos, and maintain a personal favourites list within their session so they can curate and revisit their best memories from the wedding.

## Scenarios in scope
1. Guest downloads a single photo at original resolution
2. Guest downloads all face-search result photos as a ZIP archive (up to 200 photos)
3. Guest generates a shareable link to a specific photo and shares it
4. Recipient opens shareable link — event authentication is required before the photo is shown; the link does not bypass auth
5. Shareable link opened after 72-hour expiry — link is shown as expired with a link to the event homepage
6. Guest marks a photo as favourite / unmarks it
7. Guest views their My Favourites list (all favourited photos in one view)
8. Guest's favourites persist across page refreshes within the same session
9. Guest downloads all their favourited photos as a ZIP archive from the My Favourites view

## User stories / use cases

**Scenario 1 — Single photo download**
- As a guest, I want to download the original high-resolution photo of myself, so that I have the best quality copy for printing or keeping.

**Scenario 2 — Bulk ZIP download**
- As a guest, I want to download all photos I appear in as a single ZIP archive, so that I can save my entire set of photos in one action instead of downloading them one at a time.
- As a guest whose face search returned more than 200 photos, I want to be clearly informed that my ZIP contains only the top 200 matches, so that I understand the scope of my download.

**Scenario 3 — Shareable link generation**
- As a guest, I want to generate a shareable link to a specific photo, so that I can send it to family members who want to see it.

**Scenario 4 — Shareable link recipient flow**
- As a recipient of a shared link, I want to be taken through event authentication before seeing the shared photo, so that I know the link was intended for an authorised audience.
- As a bride or groom, I want shareable links to remain within the event's access context, so that private wedding photos are not publicly accessible to anyone with the URL.

**Scenario 5 — Expired shareable link**
- As a recipient clicking a link that has expired, I want to see a clear message that the link is no longer valid and a way to reach the event homepage, so that I am not left on a broken page.

**Scenario 6 — Favourite / unfavourite toggle**
- As a guest, I want to mark a photo as a favourite with a single click, so that I can keep track of the shots I love most while browsing my results.
- As a guest, I want to unmark a photo as a favourite, so that I can adjust my list as I review the photos.

**Scenario 7 — My Favourites view**
- As a guest, I want to view all my favourited photos in one place, so that I can review my curated selection without scrolling through all results again.

**Scenario 8 — Favourites persistence across refreshes**
- As a guest, I want my favourites to still be present when I refresh or navigate away and return, so that I do not have to re-mark photos after a page reload.

**Scenario 9 — Bulk ZIP download of favourites**
- As a guest, I want to download all my favourited photos as a single ZIP archive from My Favourites, so that I can save my curated selection in one action.

## Functional requirements

### Scenario 1 — Single photo download
- REQ-1 (Scenario 1): The system must provide a download action on every photo visible to the guest (in face-search results and in My Favourites). Triggering it initiates a download of the original-resolution image from local SSD storage.
- REQ-2 (Scenario 1): Downloads must serve the original image file, not a thumbnail or compressed proxy. The `Content-Disposition` header must set `attachment` with the original filename.
- REQ-3 (Scenario 1): The download endpoint must validate that the guest's session token is scoped to the same `event_id` as the requested photo before serving the file.

### Scenario 2 — Bulk ZIP download
- REQ-4 (Scenario 2): The system must provide a "Download All" action on the face-search results page that triggers a server-side ZIP generation for all photos in the guest's result set, up to a maximum of 200 photos.
- REQ-5 (Scenario 2): If the face-search result set contains more than 200 photos, the ZIP is generated from the top 200 photos ranked by match score. A notice is displayed to the guest before and after the download explaining that only the top 200 are included.
- REQ-6 (Scenario 2): ZIP generation is server-side and streaming — the response is streamed to the client; the backend must not buffer the entire archive in memory before responding.
- REQ-7 (Scenario 2): Each file inside the ZIP uses the original filename. The ZIP filename follows the format `wedding-{event-slug}-my-photos.zip`.
- REQ-8 (Scenario 2): The bulk download endpoint must validate the guest's session token and confirm all requested photo IDs belong to the same `event_id` before streaming the archive.
- REQ-9 (Scenario 2): There is no per-guest download count limit for MVP.

### Scenario 3 — Shareable link generation
- REQ-10 (Scenario 3): The system must provide a "Share" action on every photo visible to the guest. Triggering it returns a signed URL unique to that photo.
- REQ-11 (Scenario 3): Shareable links are event-scoped signed URLs. The signature encodes `photo_id`, `event_id`, and an expiry timestamp. The backend validates the signature on every access.
- REQ-12 (Scenario 3): Shareable links expire 72 hours after creation (fixed window from creation time, not from first access). After expiry the link must return a structured error response and not expose the photo.
- REQ-13 (Scenario 3): A shareable link can only be generated for photos that belong to the guest's own event (validated via session token).

### Scenario 4 — Shareable link recipient flow
- REQ-14 (Scenario 4): When a recipient opens a shareable link, the backend verifies the link signature before routing. The frontend then presents the event's configured authentication gate (access code or OTP for protected events; no gate for public events) before displaying the photo.
- REQ-15 (Scenario 4): A valid shareable link does not grant event access. It routes the recipient to the correct event entry point; existing event authentication rules apply.
- REQ-16 (Scenario 4): After successful event authentication, the recipient is taken directly to the shared photo view.

### Scenario 5 — Expired shareable link
- REQ-17 (Scenario 5): When a shareable link is opened after its 72-hour expiry, the backend returns an error response indicating the link has expired. The frontend renders an "expired link" page with a link to the event homepage.
- REQ-18 (Scenario 5): The expired-link page must not expose any photo content, photo ID, or event metadata beyond a link to the event homepage.

### Scenario 6 — Favourite / unfavourite toggle
- REQ-19 (Scenario 6): Each photo in the guest's results set must display a favourite toggle (e.g., a heart icon). Clicking it marks the photo as a favourite; clicking again unmarks it. The UI must reflect the current state immediately.
- REQ-20 (Scenario 6): Favourite state is stored server-side in the guest's session state, keyed by `event_id` + `photo_id`. It is not persisted to PostgreSQL as a permanent record.
- REQ-21 (Scenario 6): Favourite state is scoped strictly to the guest's session token. Different sessions for the same event share no favourite state.

### Scenario 7 — My Favourites view
- REQ-22 (Scenario 7): The system must provide a My Favourites page that displays all photos the guest has marked as favourite within their current session.
- REQ-23 (Scenario 7): Photos in the My Favourites view must be displayed with the same single-photo download and share actions available in the face-search results view.
- REQ-24 (Scenario 7): If the guest has no favourited photos, the My Favourites page must display an empty state message explaining how to add favourites.

### Scenario 8 — Favourites persistence across page refreshes
- REQ-25 (Scenario 8): Favourite state must survive page refresh and in-session navigation as long as the guest's session token remains valid (24-hour idle window).
- REQ-26 (Scenario 8): When the session expires, all favourite state is cleared. The guest is not notified of this data loss proactively; the empty My Favourites page after re-authentication is the expected behaviour.

### Scenario 9 — Bulk ZIP download of favourites
- REQ-27 (Scenario 9): The My Favourites view must include a "Download All Favourites as ZIP" action that triggers server-side ZIP generation for all photos in the guest's current favourites list, subject to the same 200-photo cap as the face-search bulk download (REQ-4).
- REQ-28 (Scenario 9): The favourites ZIP endpoint must validate the guest's session token and confirm all photo IDs in the favourites list belong to the same `event_id` before streaming the archive. The ZIP filename follows the format `wedding-{event-slug}-my-favourites.zip`. ZIP generation is streaming — the backend must not buffer the full archive in memory.
- REQ-29 (Scenario 9): If the guest has no favourited photos, the "Download All Favourites as ZIP" action is hidden or disabled — it must not trigger a ZIP request for an empty set.

## Non-functional requirements
- NFR-1: Single photo download response must begin within 2 seconds of the request for photos stored on local SSD.
- NFR-2: ZIP archive for 100 photos must be fully streamed to the client in under 30 seconds on the deployment VM (4 cores, 16 GB RAM, local SSD).
- NFR-3: Shareable link signature generation and validation must not add more than 100 ms latency to the photo view endpoint.
- NFR-4: All download and share endpoints must enforce event-scoped session validation — no photo from another event must ever be served, regardless of a valid signature.
- NFR-5: ZIP streaming must not buffer the full archive in memory; peak memory usage per ZIP request must remain bounded regardless of photo count (up to 200).
- NFR-6: The system must handle concurrent ZIP generation requests without degrading single-photo download response times materially.

## Context

**Dependencies**
- Guest Access feature: all photo action endpoints require a valid guest session token issued by the Guest Access feature (`type: guest` JWT, `sub` = `event_id`). The `get_validated_guest_event` dependency must be used on every endpoint in this feature.
- Face Recognition Search feature: the ZIP bulk download operates on the photo ID result set returned by face search. The photo IDs must be passed explicitly by the client; the backend re-validates ownership against `event_id` before serving.

**Architectural notes**
- Original photos are stored on local SSD at `STORAGE_PATH`. The backend streams files directly from disk using FastAPI's `FileResponse` or a streaming `StreamingResponse`.
- Shareable link signatures use HMAC with the deployment `SECRET_KEY`; the signed payload includes `photo_id`, `event_id`, and `exp` (Unix timestamp). Expiry is a fixed 72-hour window measured from creation time.
- Favourite state lives in server-side session state (in-process or PostgreSQL-backed session store, consistent with the guest session token design in `docs/decisions/2026-06-19-guest-session-token-design.md`). No separate favourites table is created.
- ZIP generation uses Python's `zipfile` module with streaming writes. Files are read sequentially from SSD and written into the stream; the archive is never materialised fully in memory.
- All endpoints follow the `/api/v1/` prefix convention and must be documented in the backend OpenAPI schema.

**Access model**
- Guests are anonymous (no email, no user account). Session tokens are JWT-based with a 24-hour idle expiry and a sliding refresh window.
- Shareable links carry their own signed payload and do not carry a guest token; they are a separate auth surface and must be validated independently of the recipient's session.
- For public events, a shareable link takes the recipient directly to the shared photo view with no authentication step.

## Out of scope
- Favourites persisting across sessions or devices — no cross-session or cross-device sync for MVP.
- Downloading photos from the album browse view — download is available only from face-search results and My Favourites.
- Bulk download of an entire event album not scoped to face-search results — future scope.
- Download analytics tracked per photo (download counts, guest attribution) — covered by the Admin Platform epic.
- Social media sharing (native share sheet, direct-to-Instagram, etc.) — future scope.
- Email or SMS delivery of shareable links by the platform — the guest copies and pastes the link manually.

## Open questions
- [x] OQ-1: Should the My Favourites view include a "Download All Favourites as ZIP" action? — **Resolved: Yes, include for MVP (Scenario 9 added).**
- [x] OQ-2: Do shareable links require event auth for all event modes? — **Resolved: Yes for protected modes (access-code, OTP); public events skip auth and go directly to the photo (AC-12).**
- [x] OQ-3: What is the ZIP filename format? — **Resolved: `wedding-{event-slug}-my-photos.zip` for face-search ZIP; `wedding-{event-slug}-my-favourites.zip` for favourites ZIP.**
- [x] OQ-4: Does the 72-hour shareable link expiry count from creation or first access? — **Resolved: From creation (fixed window).**

## Acceptance criteria

**Scenario 1 — Single photo download**
- AC-1 (Scenario 1): Given an authenticated guest clicks the download action on a photo in their face-search results, the browser initiates a download of the original-resolution image within 2 seconds.
- AC-2 (Scenario 1): Given a guest attempts to download a photo belonging to a different `event_id`, the backend returns 403 and no file data is served.
- AC-3 (Scenario 1): Given a guest with an expired session token attempts a download, the backend returns 401 and redirects the frontend to the event entry screen.

**Scenario 2 — Bulk ZIP download**
- AC-4 (Scenario 2): Given a guest's face-search result set contains 50 photos, clicking "Download All" triggers a streamed ZIP download named `wedding-{event-slug}-my-photos.zip` containing all 50 original-resolution photos, completing in under 30 seconds.
- AC-5 (Scenario 2): Given a guest's face-search result set contains more than 200 photos, a notice is displayed stating that only the top 200 matches will be included in the ZIP, and the downloaded ZIP contains exactly 200 photos ordered by descending match score.
- AC-6 (Scenario 2): Given the ZIP request includes a photo ID belonging to a different event, the backend rejects the entire request with 403 and no archive is served.
- AC-7 (Scenario 2): Given a ZIP generation request, the backend begins streaming response bytes to the client without first accumulating the full archive in memory.

**Scenario 3 — Shareable link generation**
- AC-8 (Scenario 3): Given an authenticated guest clicks "Share" on a photo, a shareable link is returned and displayed within the UI for the guest to copy.
- AC-9 (Scenario 3): Given the same photo, two separately generated shareable links are each independently valid and independently expirable.
- AC-10 (Scenario 3): Given a guest attempts to generate a shareable link for a photo from a different `event_id`, the backend returns 403.

**Scenario 4 — Shareable link recipient flow**
- AC-11 (Scenario 4): Given a recipient opens a valid, non-expired shareable link for an event in `access-code` mode, they are shown the access code entry screen before the photo.
- AC-12 (Scenario 4): Given a recipient opens a valid, non-expired shareable link for an event in `public` mode, they are taken directly to the shared photo view with no authentication prompt.
- AC-13 (Scenario 4): Given a recipient successfully authenticates via the event entry flow after following a shareable link, they are taken to the specific shared photo, not to the general gallery.

**Scenario 5 — Expired shareable link**
- AC-14 (Scenario 5): Given a shareable link is opened more than 72 hours after creation, the frontend renders an "expired link" page with no photo content and includes a link to the event homepage.
- AC-15 (Scenario 5): Given an expired shareable link, the backend returns a structured error response (e.g., HTTP 410 Gone or 403 with `"detail": "link_expired"`) — the photo is never served.

**Scenario 6 — Favourite / unfavourite toggle**
- AC-16 (Scenario 6): Given a guest clicks the favourite toggle on an unmarked photo, the toggle state changes to favourited immediately in the UI without a page reload.
- AC-17 (Scenario 6): Given a guest clicks the favourite toggle on a favourited photo, the toggle state changes to unfavourited immediately in the UI without a page reload.
- AC-18 (Scenario 6): Given two different guests (separate session tokens) access the same event, marking a photo as favourite in one session has no effect on the other session's favourite state.

**Scenario 7 — My Favourites view**
- AC-19 (Scenario 7): Given a guest has favourited three photos, navigating to My Favourites shows exactly those three photos with single-photo download and share actions available.
- AC-20 (Scenario 7): Given a guest has no favourited photos, the My Favourites page displays a clear empty state explaining how to mark favourites.
- AC-21 (Scenario 7): Given a guest unfavourites a photo while on the My Favourites page, that photo is removed from the view immediately without a page reload.

**Scenario 8 — Favourites persistence across refreshes**
- AC-22 (Scenario 8): Given a guest has favourited photos and then refreshes the page, their My Favourites view shows the same set of photos after the reload.
- AC-23 (Scenario 8): Given a guest's session has expired and they re-authenticate, the My Favourites view is empty (previous session's favourites are not carried over).

**Scenario 9 — Bulk ZIP download of favourites**
- AC-24 (Scenario 9): Given a guest has favourited photos and clicks "Download All Favourites as ZIP" on the My Favourites page, the browser initiates a streamed ZIP download named `wedding-{event-slug}-my-favourites.zip` containing all favourited photos at original resolution.
- AC-25 (Scenario 9): Given a guest has no favourited photos, the "Download All Favourites as ZIP" action is hidden or disabled and does not trigger any backend request.
- AC-26 (Scenario 9): Given the favourites ZIP request includes a photo ID belonging to a different `event_id`, the backend rejects the entire request with 403 and no archive is served.
