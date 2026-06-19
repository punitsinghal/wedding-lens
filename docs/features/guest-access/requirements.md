## Epic
docs/epics/guest-access/EPIC.md

## Purpose
Enable wedding guests to authenticate into a specific event's photo gallery — via access code, magic link OTP, or public album — without creating an account, so that only invited guests can view photos while the entry experience remains frictionless from a QR code scan.

## Scenarios in scope
1. Guest enters an access code to gain entry (owner-set shared code, event mode: `access-code`)
2. Guest authenticates via OTP code (system-generated 6-char code, shared out-of-band by owner, event mode: `magic-link-otp`)
3. Guest accesses a public album with no authentication (event mode: `public`)
4. Guest arrives via QR code scan and is routed to the correct event entry point
5. Guest session expires after 24 hours of idle time
6. Event owner revokes all guest access, invalidating active sessions
7. Guest exceeds 3 failed code entry attempts and is locked out for 15 minutes

## User stories / use cases
- As a guest, I want to enter an access code from my wedding invitation, so that I can view photos without creating an account.
- As a guest, I want to enter an OTP code shared with me via WhatsApp or email, so that I can securely access the gallery from any device.
- As a guest, I want to scan a QR code from the invitation and land directly on the event entry screen, so that I don't have to type a URL.
- As a guest, I want to access a public wedding album immediately on arrival, so that I can browse photos without any friction.
- As a bride/groom, I want to revoke all active guest sessions at any time, so that I can restrict access after the event period ends.
- As a bride/groom, I want brute-force attempts on the access code to be automatically blocked, so that the gallery is protected from unauthorised access.

## Functional requirements

### Scenario 1 — Access code entry
1. REQ-1 (Scenario 1): When an event's access mode is `access-code`, guests navigating to the event URL must be presented with an access code entry screen before reaching the gallery.
2. REQ-2 (Scenario 1): The access code is a single shared code set by the owner; any guest with the correct code gains entry.
3. REQ-3 (Scenario 1): On correct code entry, the system issues a guest session token scoped to that `event_id` and redirects the guest to the gallery.
4. REQ-4 (Scenario 1): On incorrect code entry, the system returns an error message and increments the failure counter for that client (see Scenario 7).
5. REQ-5 (Scenario 1): Access code comparison must be case-insensitive.

### Scenario 2 — OTP code entry
6. REQ-6 (Scenario 2): When an event's access mode is `magic-link-otp`, guests navigating to the event URL must be presented with an OTP code entry screen before reaching the gallery.
7. REQ-7 (Scenario 2): The OTP code is a system-generated 6-character alphanumeric code; the owner copies it from the dashboard and distributes it to guests via WhatsApp or email outside the platform.
8. REQ-8 (Scenario 2): The system does not send any email or SMS on behalf of the guest; there is no email input field in the guest-facing OTP flow.
9. REQ-9 (Scenario 2): The OTP code has no time expiry; it remains valid until the owner revokes access or regenerates the code.
10. REQ-10 (Scenario 2): On correct OTP entry, the system issues a guest session token scoped to that `event_id` and redirects the guest to the gallery.
11. REQ-11 (Scenario 2): On incorrect OTP entry, the system returns an error and increments the failure counter for that client (see Scenario 7).
12. REQ-12 (Scenario 2): Guest identity is not stored — no email address or personal identifier is collected or persisted during the OTP flow.

### Scenario 3 — Public album
13. REQ-13 (Scenario 3): When an event's access mode is `public`, guests navigating to the event URL land directly in the gallery with no authentication step.
14. REQ-14 (Scenario 3): Public events still enforce event-scoped isolation — a guest cannot access another event's data regardless of access mode.

### Scenario 4 — QR code routing
15. REQ-15 (Scenario 4): The QR code URL routes the guest to the correct event's entry page, presenting whichever access flow is configured for that event.
16. REQ-16 (Scenario 4): QR code scanning does not bypass any configured authentication — it is a routing mechanism only.
17. REQ-17 (Scenario 4): If the event is unpublished, suspended, or in soft-delete grace period, a guest arriving via QR code receives an informative unavailable message, not a broken page.

### Scenario 5 — Session expiry
18. REQ-18 (Scenario 5): Guest sessions expire after 24 hours of idle time; the idle clock resets on each authenticated request.
19. REQ-19 (Scenario 5): On session expiry, the guest is redirected to the event's entry screen to re-authenticate.
20. REQ-20 (Scenario 5): The 24-hour idle expiry is a deployment-level configuration, not configurable per event.

### Scenario 6 — Owner revokes access
21. REQ-21 (Scenario 6): The event owner can revoke all guest access for their event at any time from the event management UI.
22. REQ-22 (Scenario 6): Revocation immediately invalidates all active guest sessions for that event.
23. REQ-23 (Scenario 6): After revocation, new access attempts are blocked until the owner re-enables access; the existing access code and OTP code are not changed by revocation.
24. REQ-24 (Scenario 6): Revocation does not delete the event or any photos.

### Scenario 7 — Lockout after failed attempts
25. REQ-25 (Scenario 7): After 3 consecutive failed code entry attempts from the same client, the system blocks further attempts from that client for 15 minutes.
26. REQ-26 (Scenario 7): The lockout applies to both access code entry (Scenario 1) and OTP code entry (Scenario 2) failures.
27. REQ-27 (Scenario 7): The lockout is per client (IP address) to avoid blocking other guests sharing the same event.
28. REQ-28 (Scenario 7): After the 15-minute cooldown, the client may attempt entry again; the failure counter resets.

## Non-functional requirements
- NFR-1: Guest can gain access from QR scan to gallery in under 60 seconds.
- NFR-2: Zero cross-event data leakage — all session tokens are scoped to a single `event_id` and must be validated on every request.
- NFR-3: Rate limiting must be applied to code entry endpoints to prevent automated brute-force attacks beyond the per-client lockout.
- NFR-4: Guest identity (email or any PII) must not be persisted at any point in any access flow.

## Context
- Guest sessions are anonymous — no user accounts, no stored identity (architectural constraint from `docs/architecture/constraints.md`).
- The three access modes (`access-code`, `magic-link-otp`, `public`) are set per event by the owner during event creation or editing (defined in Event Management grooming).
- The backend issues guest session tokens as JWTs scoped to `event_id`; the frontend sends these as `Bearer` tokens on all subsequent gallery requests.
- The platform runs on a single VM; session storage and lockout state must be handled by the backend (PostgreSQL or in-process cache).
- OTP code generation and display to the owner is a dashboard concern (Photographer Dashboard / Event Management epics); this feature covers only guest-side entry.

## Out of scope
- OTP or access code delivery via email or SMS by the platform — distribution is the owner's responsibility via WhatsApp or email outside the system.
- Per-guest access codes — all guests share a single code per event.
- Magic links (pre-authenticated URLs) — OTP mode requires the guest to enter a code; URL-based auto-authentication is not in scope.
- Photographer and event owner authentication — covered by the auth contract in `docs/architecture/constraints.md`.
- Guest analytics (who accessed, when) — covered by the Admin Platform epic.

## Open questions
All resolved during grooming session on 2026-06-19.

## Acceptance criteria
- AC-1 (Scenario 1): Given an event in `access-code` mode, a guest navigating to the event URL sees a code entry screen, not the gallery.
- AC-2 (Scenario 1): Given the correct access code (case-insensitive), the guest is issued a session token and redirected to the gallery.
- AC-3 (Scenario 1): Given an incorrect access code, the guest sees an error message and the failure counter increments.
- AC-4 (Scenario 2): Given an event in `magic-link-otp` mode, a guest navigating to the event URL sees an OTP code entry screen with no email input field.
- AC-5 (Scenario 2): Given the correct 6-character OTP code, the guest is issued a session token and redirected to the gallery.
- AC-6 (Scenario 2): Given an incorrect OTP code, the guest sees an error message and the failure counter increments.
- AC-7 (Scenario 3): Given an event in `public` mode, a guest navigating to the event URL lands directly in the gallery with no authentication prompt.
- AC-8 (Scenario 4): Given a guest scans the event QR code, they are routed to the entry screen matching the event's configured access mode.
- AC-9 (Scenario 4): Given a guest scans the QR code for a suspended or unpublished event, they see an informative unavailable message.
- AC-10 (Scenario 5): Given a guest session has been idle for 24 hours, their next request redirects them to the event entry screen.
- AC-11 (Scenario 5): Given an authenticated guest makes a request, the idle timer resets to 24 hours.
- AC-12 (Scenario 6): Given an owner revokes access, all guests with active sessions are immediately logged out on their next request.
- AC-13 (Scenario 6): Given access is revoked, a guest attempting to enter the correct access code is blocked until the owner re-enables access.
- AC-14 (Scenario 7): Given a client makes 3 consecutive failed code entry attempts, further attempts from that client are blocked for 15 minutes.
- AC-15 (Scenario 7): Given a client is locked out, other guests from different IP addresses can still attempt entry normally.
- AC-16 (Scenario 7): Given 15 minutes have elapsed since lockout, the client may attempt entry again.
