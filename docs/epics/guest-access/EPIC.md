# Guest Access

**Status:** Done
**Owner:** Product Team
**Last Updated:** 2026-06-20

## Summary
Provide flexible, secure entry points for wedding guests to access the photo gallery — via access code, magic link with OTP, or public album — while ensuring only invited guests can reach private events.

## Requirements
1. Option A — Access Code: Guest navigates to event URL and enters a code provided on their wedding invitation.
2. Option B — Magic Link / OTP: Guest enters their email address, receives a one-time passcode, and gains access after verification.
3. Option C — Public Album: Event owner can mark an event as public, requiring no login or code.
4. QR code on wedding invitation deep-links directly to the event album page.
5. Guests must not be able to access other events' photos regardless of access method.
6. Sessions must expire after a configurable idle period.
7. Event owner can revoke guest access (invalidate codes/sessions) at any time.

## User Stories

### GUEST-1 — Access Code Entry ✅ Done
**As a guest, I want to enter an access code from my wedding invitation, so that I can view the photos without creating an account.**

Acceptance Criteria:
- [ ] Code entry screen shown when event `access_mode` is `access-code`
- [ ] Validation is case-insensitive
- [ ] On success: guest JWT issued, stored in `localStorage` as `wl_guest_{eventId}`, redirected to gallery
- [ ] On failure: clear error shown; after 3 failures from same IP the form is locked for 15 minutes
- [ ] Locked-out state shows time-remaining message (HTTP 429 → frontend displays message)

---

### GUEST-2 — QR Code Deep-Link ✅ Done
**As a guest, I want to scan a QR code from the invitation, so that I land directly on the wedding album without typing anything.**

Acceptance Criteria:
- [ ] QR code encodes URL `{FRONTEND_URL}/g/{slug}`
- [ ] Scanning lands on the access code / OTP entry screen for the correct event
- [ ] Public events skip the entry screen and go straight to the gallery
- [ ] Photographer can download the QR code PNG from the dashboard

---

### GUEST-3 — Public Album ✅ Done
**As a bride/groom, I want to mark my event as public so guests can browse without any code.**

Acceptance Criteria:
- [ ] `access_mode = public` events auto-redirect from `/g/[slug]` to gallery
- [ ] No PIN / code entry screen shown
- [ ] Gallery endpoints accept empty or absent guest token for public events

---

### GUEST-4 — Session Expiry & Refresh ✅ Done
**As a guest, I want my session to stay alive while I'm actively browsing, but expire after a period of inactivity, so my access is appropriately time-limited.**

Acceptance Criteria:
- [ ] Guest JWT has configurable TTL (default 24h via `GUEST_SESSION_IDLE_TTL_SECONDS`)
- [ ] Each authenticated API request auto-refreshes the token (new JWT in `X-Guest-Token` response header)
- [ ] Frontend captures and stores refreshed token transparently
- [ ] Expired token returns 401; frontend redirects back to access-code entry

---

### GUEST-5 — Session Revocation ✅ Done
**As a bride/groom, I want to revoke all active sessions so the gallery is no longer accessible after the event.**

Acceptance Criteria:
- [ ] `POST /api/v1/events/{event_id}/revoke-guest-access` sets revocation timestamp
- [ ] Any guest token issued before the revocation timestamp is rejected with 401
- [ ] `POST /api/v1/events/{event_id}/enable-guest-access` reinstates access
- [ ] Photographer dashboard exposes both actions

---

## Features

| Feature | Status |
|---------|--------|
| Access code entry screen and validation | ✅ Done |
| QR code generation and deep-link routing | ✅ Done |
| Public album mode (no auth required) | ✅ Done |
| Session management and idle expiry | ✅ Done |
| Session revocation by event owner | ✅ Done |
| Rate limiting on access code attempts | ✅ Done |

## Success Metrics
- Guest can gain access to the correct event in under 60 seconds from scanning QR code.
- Zero cross-event data leakage incidents.

## Decisions

- **2026-06-20:** Email delivery is out of scope. OTP codes are distributed out-of-band by the photographer (e.g., printed on the invitation). The `magic-link-otp` access mode is effectively a second access code type (auto-generated 6-char alphanumeric), not a true email-delivered magic link.
- **2026-06-20:** OTP codes are stable per event (not per request) — generated once and stored on the event record. Suitable given out-of-band distribution; no single-use invalidation needed.
- **2026-06-20:** Rate limiting is in-process (not Redis). Suitable for single-VM deployment; would need to migrate to Redis-backed if multiple backend replicas are added.
- **2026-06-20:** No guest PII stored in the database — no guest accounts, no email storage. Tokens are ephemeral JWTs in `localStorage` only.
- **2026-06-20:** Pre-expiry session warning UI is out of scope. Sessions expire silently; guests are redirected to the access code entry screen on 401.

## Open Questions
- [ ] **#1** What is the default session expiry period? — **Current default:** 24h (`GUEST_SESSION_IDLE_TTL_SECONDS`). Owner: Product to confirm if this is correct.
- [x] **#2** ~~Should magic link OTP support SMS in addition to email?~~ — Closed: email delivery is out of scope entirely; OTP is distributed out-of-band.
- [ ] **#3** How many failed access code attempts trigger a lockout? — **Current default:** 3 attempts, 15-min lockout. Owner: Engineering to confirm.
- [x] **#4** ~~For `magic-link-otp` events, should OTP be sent to any email?~~ — Closed: no email sending; OTP shared out-of-band by photographer.
- [x] **#5** ~~Should OTP be per-request or per-event?~~ — Closed: per-event (stable code), no single-use invalidation needed.
