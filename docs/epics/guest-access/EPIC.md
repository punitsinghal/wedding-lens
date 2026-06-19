# Guest Access

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

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
- As a guest, I want to enter an access code from my wedding invitation, so that I can view the photos without creating an account.
- As a guest, I want to receive a magic link via email OTP, so that I can securely access the gallery from any device.
- As a guest, I want to scan a QR code from the invitation, so that I land directly on the wedding album without typing anything.
- As a bride/groom, I want to choose between access-code, magic-link, or public access for my event, so that I can match the level of privacy I need.
- As a bride/groom, I want to revoke all active sessions if I need to restrict access post-event, so that the gallery is no longer publicly accessible.

## Features
| Feature | Status |
|---------|--------|
| Access code entry screen and validation | Backlog |
| Magic link / email OTP flow | Backlog |
| Public album mode (no auth required) | Backlog |
| QR code generation and deep-link routing | Backlog |
| Session management and idle expiry | Backlog |
| Session revocation by event owner | Backlog |
| Rate limiting on access code attempts | Backlog |

## Success Metrics
- Guest can gain access to the correct event in under 60 seconds from scanning QR code.
- OTP delivery time under 30 seconds at p95.
- Zero cross-event data leakage incidents.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] What is the default session expiry period? — owner: Product Team
- [ ] Should magic link OTP use email only, or also support SMS? — owner: Product Team
- [ ] How many failed access code attempts trigger a lockout? — owner: Engineering
