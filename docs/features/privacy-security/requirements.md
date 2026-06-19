## Epic
docs/epics/privacy-security/EPIC.md

## Purpose
Establish the user-facing consent and data governance layer for WeddingLens so that biometric face data is collected only with informed agreement, guests retain meaningful control over their data, and the platform meets its obligations under GDPR (the broadest applicable framework). Technical controls — embedding encryption and selfie auto-deletion — are implemented in the AI Face Processing and Face Recognition Search epics; this feature captures the governance requirements that surround them.

## Scenarios in scope
1. Event owner confirms guest consent before publishing the event (consent checkbox in publish pre-flight)
2. Guest views the platform privacy notice and acknowledges it before the selfie camera activates
3. Guest submits a face data removal request via a form on the event page
4. Admin receives and fulfills a face data removal request within 24 hours
5. Rate limiting blocks a guest who submits excessive selfie upload or search requests
6. All guest and photographer API traffic travels over TLS 1.2+
7. Face embedding encryption is verified in a storage audit

## User stories / use cases

**Scenario 1 — Event owner consent**
- As an event owner, I want to confirm that my guests have been informed about face recognition before I publish the gallery, so that I take explicit responsibility for biometric data collection under the event I own.

**Scenario 2 — Guest privacy notice**
- As a guest, I want to read the platform's biometric data privacy notice before I upload my selfie, so that I know what data is collected, why, and how long it is kept — and I can choose not to proceed if I disagree.

**Scenario 3 — Guest removal request submission**
- As a guest, I want to submit a request to have my face data removed from the event index, so that I can exercise my right to erasure without needing a platform account.

**Scenario 4 — Admin fulfillment**
- As an admin, I want to receive face data removal requests with sufficient detail to locate and delete the relevant embeddings, so that I can fulfill the request within the required 24-hour window.

**Scenario 5 — Rate limiting**
- As the platform, I want to limit how many selfie upload and search requests a guest session can make in a short window, so that I prevent enumeration attacks and resource abuse without blocking legitimate guests.

**Scenario 6 — TLS enforcement**
- As a guest or photographer, I want all communication with the backend to be encrypted in transit, so that my photos, selfie, and session tokens cannot be intercepted.

**Scenario 7 — Embedding encryption audit**
- As the platform operator, I want a verifiable signal that face embeddings are encrypted at rest in Qdrant, so that I can confirm the encryption control is active during storage audits.

## Functional requirements

### Scenario 1 — Event owner consent confirmation
1. REQ-1 (Scenario 1): The event publish flow must include a pre-flight consent checkbox with the exact label: "I confirm that guests attending this event have been informed that their photos will be processed using face recognition to help them find themselves in the gallery."
2. REQ-2 (Scenario 1): The publish action must be disabled until the checkbox is checked; checking it must be an explicit user gesture (not pre-ticked).
3. REQ-3 (Scenario 1): The backend must record the consent confirmation (event_id, timestamp, confirming user identity) in PostgreSQL at the moment the event is published.
4. REQ-4 (Scenario 1): If an event is unpublished and republished, the consent checkbox must be presented again and a new confirmation record must be stored.

### Scenario 2 — Guest privacy notice and acknowledgement
5. REQ-5 (Scenario 2): The selfie upload screen must display a summary privacy notice before the camera activates, covering: what biometric data is collected (face embedding), the purpose (finding the guest in event photos), retention (selfie deleted immediately after search; embeddings deleted when the event is purged), and a link to the full platform privacy notice at `/privacy`.
6. REQ-6 (Scenario 2): The camera must not activate until the guest taps an explicit "I understand, continue" acknowledgement button.
7. REQ-7 (Scenario 2): The full platform biometric data privacy notice must be published at the `/privacy` route and must be accessible without authentication.
8. REQ-8 (Scenario 2): The privacy notice linked from the selfie screen must describe: data collected, legal basis (consent), data controller identity, retention periods, and how to submit a removal request.

### Scenario 3 — Guest face data removal request submission
9. REQ-9 (Scenario 3): The event page must include a "Remove my face data" link accessible to any guest who has reached the event (authenticated via event code or OTP).
10. REQ-10 (Scenario 3): The removal request form must collect: the guest's name, an email address for confirmation, and a free-text description of when they uploaded a selfie (to assist admin lookup).
11. REQ-11 (Scenario 3): On submission, the backend must store the removal request (event_id, submitted_at, name, email, description, status: "pending") in PostgreSQL.
12. REQ-12 (Scenario 3): The guest must receive an on-screen confirmation that the request has been received and will be processed within 24 hours.

### Scenario 4 — Admin fulfillment of removal request
13. REQ-13 (Scenario 4): The admin must be notified of new removal requests; the notification mechanism (email, dashboard flag) is an implementation decision.
14. REQ-14 (Scenario 4): The removal request record must expose sufficient fields (event_id, submitted_at, description) for the admin to identify the target embeddings in Qdrant and delete them.
15. REQ-15 (Scenario 4): The admin must be able to mark a request as "fulfilled" and record the fulfillment timestamp; this update must be persisted in PostgreSQL.
16. REQ-16 (Scenario 4): Fulfilled requests must be retained in the database for audit purposes — they must not be deleted.

### Scenario 5 — Rate limiting
17. REQ-17 (Scenario 5): The selfie upload endpoint (`POST /api/v1/search/upload` or equivalent) must enforce a limit of 10 requests per guest session per 5-minute sliding window.
18. REQ-18 (Scenario 5): The face search endpoint (`POST /api/v1/search` or equivalent) must enforce the same limit: 10 requests per guest session per 5-minute sliding window.
19. REQ-19 (Scenario 5): When the limit is exceeded, the backend must return HTTP 429 with a `Retry-After` header indicating when the window resets.
20. REQ-20 (Scenario 5): The frontend must display a human-readable message when it receives a 429, informing the guest how long to wait before trying again.

### Scenario 6 — TLS enforcement
21. REQ-21 (Scenario 6): The backend must refuse non-TLS HTTP connections in production; all traffic must be served over HTTPS (TLS 1.2 minimum, TLS 1.3 preferred).
22. REQ-22 (Scenario 6): TLS termination is handled at the infrastructure layer (Nginx + Let's Encrypt); the backend must be configured to trust the proxy and reject direct non-TLS connections.
23. REQ-23 (Scenario 6): The `Strict-Transport-Security` (HSTS) header must be set on all responses with a minimum `max-age` of 31536000 seconds.

### Scenario 7 — Embedding encryption audit
24. REQ-24 (Scenario 7): The backend must expose an internal health/audit endpoint (not publicly reachable) that returns a boolean confirming whether the Qdrant collection is configured with payload encryption enabled.
25. REQ-25 (Scenario 7): The audit endpoint must be callable by the admin without affecting stored embeddings or guest-facing operations.

## Non-functional requirements

- NFR-1: The consent checkbox must add no more than one additional screen or modal step to the event publish flow.
- NFR-2: The selfie privacy notice acknowledgement must not require navigation away from the selfie upload screen.
- NFR-3: A removal request form submission must complete within 2 seconds under normal load.
- NFR-4: Rate limit counters must be stored in a structure that survives a backend restart within a rolling 5-minute window (implementation detail: Redis or in-process sliding-window keyed on session token).
- NFR-5: The `/privacy` page must load without a backend API call — it is static content.
- NFR-6: All consent confirmation records and removal request records must be retained for a minimum of 3 years for audit purposes, independent of event lifecycle.

## Context

- Face embedding encryption at rest is implemented in the AI Face Processing epic. REQ-24 and REQ-25 add the audit surface only — this feature does not implement the encryption itself.
- Selfie auto-deletion is implemented in the Face Recognition Search epic. REQ-5 and REQ-8 reference the retention period as a fact to be displayed to guests — this feature does not implement deletion.
- Guest session identity for rate limiting is the session token issued at event entry (QR + PIN or OTP flow). The rate limiter keys on this token; guests with no valid session cannot reach the selfie upload endpoint.
- GDPR is the assumed compliance framework (broadest coverage; also satisfies PDPA and CCPA baseline requirements). This assumption must be confirmed with Legal — see Open Questions.
- The designated Data Controller identity (platform vs event owner) is unresolved and affects the wording of the privacy notice. A placeholder is acceptable for MVP; see Open Questions.
- Removal request fulfillment is a manual admin process for MVP. Automated deletion is deferred to a future phase.
- TLS configuration (Nginx, Let's Encrypt certificate renewal, HSTS) is owned by the Ops/Deployment layer. This feature's REQ-21 through REQ-23 define the backend's responsibility within that layer.
- The `/privacy` route is a Next.js static page. It does not require backend API integration.

## Out of scope
- Automated face data removal (MVP fulfillment is manual; automation is a future phase)
- Cookie consent banner — the platform uses no tracking cookies
- Right to access / data portability (GDPR Article 15) — deferred to a future phase
- Guest-facing "view my data" functionality — deferred to a future phase
- DPIA (Data Protection Impact Assessment) documentation — Legal team responsibility, not a platform deliverable
- Admin-level data audit logs (covered by the Admin Platform epic)
- DPA (Data Processing Agreement) between the platform and event owners — Legal responsibility; see Open Questions

## Open questions
- [ ] Which privacy regulation framework applies (GDPR, PDPA, CCPA, all three)? — owner: Legal / Product Team. GDPR assumed as broadest; confirm with Legal before publishing the `/privacy` notice.
- [ ] What is the retention policy for face embeddings after an event's guest-access period ends but before the owner deletes the event? — owner: Legal / Product Team. Current assumption: embeddings persist until event purge (30-day grace period after deletion).
- [ ] Should the platform publish a biometric data DPA (Data Processing Agreement) for event owners to sign? — owner: Legal.
- [ ] Who is the designated Data Controller — the platform or the event owner? — owner: Legal. Affects privacy notice wording and the consent checkbox framing.
- [ ] Should guests receive a confirmation email when their face data removal request is submitted? — owner: Product Team. An email confirmation would improve trust but requires a transactional email service; not included in MVP scope.

## Acceptance criteria

**Scenario 1 — Event owner consent**
- AC-1a: Given an event in "draft" state, when the event owner navigates to publish, then the publish button is disabled and the consent checkbox is unchecked and not pre-filled.
- AC-1b: Given the consent checkbox is unchecked, when the event owner clicks the disabled publish button, then no publish action is triggered and a tooltip or inline message indicates the checkbox is required.
- AC-1c: Given the consent checkbox is checked, when the event owner publishes the event, then the backend creates a consent record containing event_id, timestamp, and the confirming user's identity — and the event status transitions to "published."
- AC-1d: Given a previously published event is unpublished and the owner attempts to republish, then the consent checkbox is presented again and must be checked before publishing succeeds.

**Scenario 2 — Guest privacy notice**
- AC-2a: Given a guest navigates to the selfie upload screen, then the privacy notice summary is displayed before the camera component renders — the camera is not active.
- AC-2b: Given the privacy notice is displayed, when the guest has not tapped "I understand, continue," then the camera activation control is not visible or is inert.
- AC-2c: Given the guest taps "I understand, continue," then the camera activates and the selfie upload flow proceeds normally.
- AC-2d: Given any unauthenticated user navigates to `/privacy`, then the full platform biometric data privacy notice is returned with HTTP 200 and contains retention periods, legal basis, data controller identification, and removal request instructions.

**Scenario 3 — Guest removal request submission**
- AC-3a: Given a guest authenticated to an event navigates to the event page, then a "Remove my face data" link is visible.
- AC-3b: Given the guest submits the removal request form with name, email, and description, then the backend returns HTTP 200 and the guest sees an on-screen confirmation stating the request will be processed within 24 hours.
- AC-3c: Given the form is submitted, then a removal request record with status "pending," event_id, submitted_at, name, email, and description is persisted in PostgreSQL.
- AC-3d: Given the guest submits the form with a missing required field (name, email, or description), then the submission is rejected with an inline validation error and no database record is created.

**Scenario 4 — Admin fulfillment**
- AC-4a: Given a removal request with status "pending" exists, when the admin marks it as "fulfilled," then the record is updated with status "fulfilled" and a fulfillment timestamp in PostgreSQL.
- AC-4b: Given a fulfilled removal request, when queried, then the record remains in the database and is not deleted.
- AC-4c: Given the admin queries the removal request, then event_id, submitted_at, and description are present and sufficient to locate the target guest session in Qdrant.

**Scenario 5 — Rate limiting**
- AC-5a: Given a guest session submits 10 selfie upload requests within a 5-minute window, then the 11th request returns HTTP 429 with a `Retry-After` header.
- AC-5b: Given a guest session submits 10 search requests within a 5-minute window, then the 11th request returns HTTP 429 with a `Retry-After` header.
- AC-5c: Given a 429 response is received, then the frontend displays a human-readable wait message that includes the retry time — no raw HTTP status code is shown to the guest.
- AC-5d: Given 5 minutes have elapsed since the first request in the window, then the guest session can submit a new request successfully.

**Scenario 6 — TLS enforcement**
- AC-6a: Given the production backend is running, when an HTTP (non-TLS) request is sent directly to the backend port, then the connection is refused or redirected to HTTPS — no plaintext response is returned.
- AC-6b: Given a valid HTTPS request, then the response includes a `Strict-Transport-Security` header with `max-age` of at least 31536000.
- AC-6c: Given a TLS handshake, then the negotiated protocol is TLS 1.2 or higher — TLS 1.0 and 1.1 connections are rejected.

**Scenario 7 — Embedding encryption audit**
- AC-7a: Given the internal audit endpoint is called by an admin, then it returns a JSON response with a field (e.g., `embeddings_encrypted: true`) confirming that the Qdrant collection is configured with encryption enabled.
- AC-7b: Given the audit endpoint, when called from a public-facing network path, then the request is rejected (HTTP 403 or connection refused) — the endpoint is not externally accessible.
