# Privacy & Security

**Status:** Draft
**Owner:** Product Team
**Last Updated:** 2026-06-19

## Summary
Ensure the platform handles biometric face data responsibly by encrypting embeddings, auto-deleting uploaded selfies, enforcing event-scoped access, and giving guests meaningful control over their data — in compliance with privacy regulations.

## Requirements
1. Wedding owner must explicitly confirm photo-sharing consent before the event goes live.
2. Face embeddings must be encrypted at rest in the vector database.
3. Guest-uploaded selfies must be automatically deleted after the search query completes.
4. Guests must be able to request removal of their face data from the event index.
5. Events can be password-protected (access code), OTP-gated, or public.
6. Private albums must only be accessible to authenticated guests of that event.
7. All data transmission must use TLS 1.2+.
8. Face data (embeddings) must not be shared across events — strict event-scoping enforced.
9. Rate limiting must be applied to selfie upload and search endpoints to prevent abuse.

## User Stories
- As a guest, I want my uploaded selfie deleted automatically after search, so that my biometric data is not retained by the platform.
- As a guest, I want to request removal of my face data from the event index, so that I have control over my biometric information.
- As a bride/groom, I want to confirm consent before making the gallery live, so that I take responsibility for photo-sharing with my guests.
- As the platform, I want face embeddings encrypted at rest, so that a storage breach does not expose guest biometric data.
- As an admin, I want all guest data scoped strictly to its event, so that there is no cross-event data leakage.

## Features
| Feature | Status |
|---------|--------|
| Consent confirmation flow for event owner at activation | Backlog |
| Face embedding encryption at rest (Qdrant + DB layer) | Backlog |
| Auto-delete selfie after search pipeline completion | Backlog |
| Guest data removal request endpoint and fulfilment | Backlog |
| Event-scoped data isolation enforcement | Backlog |
| TLS enforcement on all endpoints | Backlog |
| Rate limiting on selfie upload and search endpoints | Backlog |
| Private album access control | Backlog |

## Success Metrics
- 100% of uploaded selfies deleted within 60 seconds of search completion.
- Zero incidents of cross-event face data access.
- Guest data removal request fulfilled within 24 hours.
- All vector embeddings confirmed encrypted at rest in storage audit.

## Decisions
<!-- Decisions made during this epic's lifetime -->

## Open Questions
- [ ] Which privacy regulation framework applies (GDPR, PDPA, CCPA)? — owner: Legal / Product Team
- [ ] What is the retention policy for face embeddings after the event period ends? — owner: Legal / Product Team
- [ ] Should the platform publish a biometric data privacy notice visible to guests before selfie upload? — owner: Legal
