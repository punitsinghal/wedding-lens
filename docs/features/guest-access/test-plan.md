## Summary

This test plan covers the guest-access feature: the three authentication modes guests use to enter an event gallery (access code, OTP code, public), QR code routing, 24-hour idle session expiry, owner-initiated access revocation, and brute-force lockout. Guest access is the gateway to every downstream guest flow (photo browsing, face search, ZIP download) — correctness here is a hard prerequisite for the rest of the platform, and zero cross-event data leakage is a mandatory security invariant.

---

## Scope

**In scope:**
- Access code entry flow (mode: `access-code`) including case-insensitive matching
- OTP code entry flow (mode: `magic-link-otp`) including no-PII guarantee
- Public album access flow (mode: `public`)
- QR code routing to the correct entry mode
- Guest session token issuance, scoping, and validation
- 24-hour idle session expiry and reset-on-request behaviour
- Owner revocation of all active guest sessions
- Per-IP lockout after 3 failed attempts, 15-minute cooldown
- Cross-event isolation (token from event A rejected on event B)
- Rate limiting on code entry endpoints (NFR-3)

**Out of scope:**
- OTP or access code delivery via email or SMS — distribution is the owner's responsibility
- Photographer and event owner authentication
- Photo browsing, face search, and ZIP download — covered by Photographer Dashboard and AI Face Processing features
- Guest analytics — covered by Admin Platform feature
- OTP code generation and display in the owner dashboard — covered by Event Management and Photographer Dashboard features

---

## Assumptions (flag for resolution)

| # | Assumption | TC affected |
|---|------------|-------------|
| A1 | ✅ Confirmed: 24-hour idle expiry is overridable via `GUEST_SESSION_IDLE_TTL_SECONDS` env var in test mode — no real-time wait required | TC-12, TC-20, TC-34 |
| A2 | ✅ Confirmed: Session revocation uses a server-side blocklist checked on every request — revocation is synchronously testable | TC-13, TC-35 |
| A3 | ✅ Confirmed: Backend trusts `X-Forwarded-For`; integration tests spoof IPs via this header to simulate distinct clients | TC-15, TC-18 |
| A4 | ✅ Confirmed: NFR-1 "QR scan to gallery under 60 seconds" is manual only (M-01) | M-01 |

---

## Test cases

### Happy path

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-01 | access-code mode — code entry screen shown before gallery | GET `/<slug>` on an `access-code` event as unauthenticated guest | Response is the code entry page, not the gallery; no gallery content returned | Yes |
| TC-02 | access-code mode — correct code issues session token | POST code entry with correct access code | 200; response contains guest session JWT scoped to `event_id`; redirect to gallery | Yes |
| TC-03 | access-code mode — case-insensitive match | POST code entry with access code in uppercase when code was set in lowercase (and vice versa) | 200; session issued; access granted | Yes |
| TC-04 | OTP mode — OTP entry screen shown, no email field | GET `/<slug>` on a `magic-link-otp` event as unauthenticated guest | Response is OTP entry page; response HTML/JSON contains no email input field | Yes |
| TC-05 | OTP mode — correct OTP grants session | POST OTP entry with correct 6-char code | 200; session JWT issued scoped to `event_id`; redirect to gallery | Yes |
| TC-06 | OTP mode — no PII persisted after entry | POST correct OTP; inspect all database tables | No email, name, phone, or personal identifier stored in any table for this guest | Yes |
| TC-07 | public mode — no auth prompt, direct gallery | GET `/<slug>` on a `public` event as unauthenticated guest | 200; gallery content returned without any code entry step | Yes |
| TC-08 | QR code routes to correct entry mode (access-code) | Fetch QR URL for `access-code` event | Landing page is code entry screen | Yes |
| TC-09 | QR code routes to correct entry mode (OTP) | Fetch QR URL for `magic-link-otp` event | Landing page is OTP entry screen | Yes |
| TC-10 | QR code routes to correct entry mode (public) | Fetch QR URL for `public` event | Landing page is gallery (no auth step) | Yes |
| TC-11 | Session token accepted on gallery requests | Issue session token; GET gallery endpoint with `Authorization: Bearer <token>` | 200; gallery content returned | Yes |
| TC-12 | Idle timer resets on authenticated request (A1) | Issue session with short TTL; make a request before expiry; wait past original TTL; make another request | Second post-original-TTL request succeeds (timer was reset); session not expired | Yes |
| TC-13 | Owner revokes access — active sessions blocked on next request (A2) | Issue guest session; owner POST revoke; use existing token on gallery request | 401 or redirect to entry screen | Yes |
| TC-14 | Revocation does not change access code or OTP | Owner revokes; inspect access code and OTP values | Codes unchanged; owner re-enables and guests can enter with same codes | Yes |
| TC-15 | Owner re-enables access after revocation — entry works | Revoke; owner POST re-enable; guest POSTs correct code | Session issued; gallery accessible | Yes |

---

### Edge cases

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-16 | Lockout after 3 failed attempts (access-code) | POST incorrect access code 3 times from same IP | 4th attempt returns 429 or lockout error; attempt blocked for 15 minutes | Yes |
| TC-17 | Lockout after 3 failed attempts (OTP) | POST incorrect OTP 3 times from same IP | 4th attempt blocked; lockout error returned | Yes |
| TC-18 | Lockout is per-IP — other IPs unaffected (A3) | Lock out IP-A with 3 failures; attempt entry from spoofed IP-B | IP-B attempt is accepted normally | Yes |
| TC-19 | Lockout lifts after 15 minutes | Lock out client; advance clock past 15 minutes; attempt entry | Entry attempt accepted; failure counter reset | Yes |
| TC-20 | Session expiry after 24h idle — redirect to entry (A1) | Issue session with short TTL; wait for TTL; make gallery request | 401 or redirect to event entry screen | Yes |
| TC-21 | OTP has no time expiry — valid until revoked | Issue OTP; wait 48h (simulated); use OTP to enter | Session issued; entry succeeds | Yes |
| TC-22 | Cross-event isolation — token from event A rejected on event B | Issue guest JWT for event A; use it on event B gallery endpoint | 401 or 403; event B content not returned | Yes |
| TC-23 | Public mode still enforces event isolation | Access public event A; attempt to request event B data using event A session | Event B data not returned | Yes |
| TC-24 | QR scan for suspended event — informative message | GET QR URL for a suspended event | Human-readable unavailable message returned; not a broken page or bare 404 | Yes |
| TC-25 | QR scan for unpublished event — informative message | GET QR URL for an unpublished event | Human-readable unavailable message returned | Yes |
| TC-26 | QR scan for soft-deleted event — informative message | GET QR URL for a soft-deleted event | Human-readable unavailable message returned | Yes |
| TC-27 | Rate limiting on code entry endpoint beyond per-client lockout (NFR-3) | Send > threshold requests per second to `/api/v1/events/{id}/auth` | 429 Too Many Requests returned; automated brute-force blocked at transport layer | Yes |

---

### Failure / error paths

| ID | Scenario | Steps | Expected result | Automated? |
|----|----------|-------|-----------------|------------|
| TC-30 | Incorrect access code — error message, counter increments | POST incorrect code; inspect failure counter | Error message returned; failure counter is 1 (verifiable via internal state or subsequent lockout behaviour) | Yes |
| TC-31 | Incorrect OTP — error message, counter increments | POST incorrect OTP; inspect failure counter | Error message returned; failure counter is 1 | Yes |
| TC-32 | Unauthenticated gallery request on access-code event | GET gallery endpoint with no token | 401; no gallery content leaked | Yes |
| TC-33 | Unauthenticated gallery request on OTP event | GET gallery endpoint with no token | 401; no gallery content leaked | Yes |
| TC-34 | Expired session rejected | Issue session with short TTL (A1); wait for expiry; GET gallery | 401 or redirect to entry screen | Yes |
| TC-35 | Revoked session rejected immediately (A2) | Issue session; owner revokes; immediately use session token | 401; no grace window | Yes |
| TC-36 | Guest attempts correct code after owner revocation | Revoke access; POST correct access code | 403 or "access revoked" error; session not issued | Yes |
| TC-37 | Tampered JWT rejected | Issue valid session JWT; modify `event_id` claim; use on gallery | 401; request rejected | Yes |
| TC-38 | JWT signed with wrong secret rejected | Craft JWT signed with a different secret; use on gallery | 401 | Yes |

---

## Acceptance criteria coverage

| Criterion | TC IDs | Status |
|-----------|--------|--------|
| AC-1: access-code mode shows code entry screen | TC-01 | Covered |
| AC-2: Correct access code issues session and redirects to gallery | TC-02, TC-03 | Covered |
| AC-3: Incorrect access code shows error, increments counter | TC-30 | Covered |
| AC-4: OTP mode shows OTP entry screen with no email field | TC-04 | Covered |
| AC-5: Correct OTP issues session and redirects to gallery | TC-05 | Covered |
| AC-6: Incorrect OTP shows error, increments counter | TC-31 | Covered |
| AC-7: public mode lands directly in gallery | TC-07 | Covered |
| AC-8: QR scan routes to entry screen matching access mode | TC-08, TC-09, TC-10 | Covered |
| AC-9: QR scan for suspended/unpublished event shows informative message | TC-24, TC-25 | Covered |
| AC-10: Idle 24h session expires and redirects to entry | TC-20 | Covered (pending A1) |
| AC-11: Authenticated request resets idle timer | TC-12 | Covered (pending A1) |
| AC-12: Owner revocation immediately blocks active sessions | TC-13, TC-35 | Covered (pending A2) |
| AC-13: Correct code blocked after revocation until re-enabled | TC-36 | Covered |
| AC-14: 3 failed attempts triggers 15-minute lockout | TC-16, TC-17 | Covered |
| AC-15: Lockout is per-IP; other IPs unaffected | TC-18 | Covered (pending A3) |
| AC-16: Lockout lifts after 15 minutes | TC-19 | Covered |

**Note on AC-9:** REQ-17 also includes soft-deleted events arriving via QR — covered by TC-26, which extends AC-9's scope.

---

## Manual test checklist

- [ ] **M-01 (NFR-1):** Scan the event QR code on both iOS and Android; time from scan to gallery page fully loaded. Confirm under 60 seconds on a standard mobile connection.
- [ ] **M-02 (AC-1):** Navigate to an `access-code` event URL in a real browser with no prior session — confirm the code entry screen renders correctly with no flash of gallery content.
- [ ] **M-03 (AC-4):** Navigate to a `magic-link-otp` event URL — confirm there is no email input field on the page.
- [ ] **M-04 (AC-7):** Navigate to a `public` event URL — confirm gallery loads with no auth prompt of any kind.
- [ ] **M-05 (AC-9):** Scan QR code for a suspended event on a mobile device — confirm a human-readable message appears (not a blank screen or raw error).
- [ ] **M-06 (AC-10):** Let a guest session sit idle; verify the redirect to entry screen happens on next interaction (using real idle TTL, not the test override).

---

## Known risks

1. **Idle TTL test override (A1):** If the backend doesn't expose a configurable idle TTL, TC-12, TC-20, and TC-34 cannot be automated and must fall back to manual tests or unit-level clock mocking. Resolve during implementation planning.

2. **Revocation latency (A2):** If revocation is implemented by rotating a signing secret rather than a blocklist, short-lived JWTs issued immediately before revocation may be valid until their embedded expiry. TC-35's "immediately" requirement may not be satisfiable without a blocklist. This is an implementation constraint that must be confirmed before build.

3. **IP-based lockout in NAT/proxy environments:** Multiple guests sharing a NAT IP (e.g., a wedding venue's Wi-Fi) could be collectively locked out by one bad actor. The requirements accept this trade-off (REQ-27), but it should be flagged in release notes.

4. **X-Forwarded-For spoofing in production:** If the backend trusts `X-Forwarded-For` without validating the proxy chain, an attacker can cycle IPs to bypass the lockout. The lockout tests (TC-16–TC-19) should verify the trust model matches the production deployment (behind a known reverse proxy).

5. **OTP no-expiry policy (REQ-9):** A valid OTP code has no time limit. If an owner forgets to revoke it, old codes remain valid indefinitely. No test can detect this drift — it is a risk to surface in owner UX guidance.

6. **Cross-event isolation under high concurrency:** TC-22 tests isolation with a single token. Under high concurrency, a subtle caching bug (e.g., event-scoped cache keyed incorrectly) could cause cross-event leakage. Consider a concurrent stress variant of TC-22 if the platform targets high-traffic events.

---

## Sign-off

- [x] All acceptance criteria covered
- [x] Edge cases documented
- [x] Manual checklist reviewed
- QA: Punit Singhal — 2026-06-19
