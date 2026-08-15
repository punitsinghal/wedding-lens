# Privacy & Security

**Status:** In Progress
**Owner:** Product Team
**Last Updated:** 2026-08-15

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
| Consent confirmation flow for event owner at activation | ✅ Done (#37) |
| Face embedding encryption at rest (Qdrant + DB layer) | ✅ Done — Postgres `embedding_enc` (AES-256-GCM) is the app-level control; Qdrant relies on infra-level encryption at rest. See `docs/decisions/2026-06-19-face-embedding-dual-storage.md` and audit endpoint (#37) |
| Auto-delete selfie after search pipeline completion | ✅ Done (Face Recognition Search epic; `face_search.py` deletes selfie bytes in a `finally` block) |
| Guest data removal request endpoint and fulfilment | ✅ Done (#37) |
| Event-scoped data isolation enforcement | ✅ Done (all Qdrant/Postgres queries scoped by `event_id`; see `test_search_scoped_to_event_id`) |
| TLS enforcement on all endpoints | Partial — backend emits HSTS and is configured to trust the proxy; actual Nginx + Let's Encrypt termination/cert renewal is Ops/Deployment work and not confirmed deployed |
| Rate limiting on selfie upload and search endpoints | ✅ Done (#37) |
| Private album access control | ✅ Done — backend visibility filter (gallery, album tabs, face search) + photographer toggle UI (commit `0f847b9`, part of #37); not part of the originally groomed requirements/design doc, tracked via EPIC requirement 6 only |

## Success Metrics
- 100% of uploaded selfies deleted within 60 seconds of search completion.
- Zero incidents of cross-event face data access.
- Guest data removal request fulfilled within 24 hours.
- All vector embeddings confirmed encrypted at rest in storage audit.

## Decisions
<!-- Decisions made during this epic's lifetime -->
- 2026-08-15: Private album visibility is enforced by query-time filtering at every guest-facing
  read path (gallery listing, album tabs, and face search) rather than in Qdrant. See
  `docs/decisions/2026-08-15-private-album-query-time-filtering.md`.

## Open Questions
- [x] Which privacy regulation framework applies? → India's DPDP Act, 2023 (platform is Data Fiduciary, guests are Data Principals). — Product, resolved 2026-06-22
- [x] What is the retention policy for face embeddings after the event period ends? → All event data (photos, face records, embeddings) deleted within 30 days of the event end date. — Product, resolved 2026-06-22
- [x] Should the platform publish a biometric data privacy notice visible to guests before selfie upload? → Yes, static `/privacy` page, English-only for MVP. — resolved 2026-06-22, shipped in #37
- [ ] Should the platform publish a biometric data DPA (Data Processing Agreement) for event owners to sign? — owner: Legal (design/process, not a build blocker)
- [ ] Should guests receive a confirmation email when their face data removal request is submitted? — owner: Product Team; MVP is on-screen confirmation only, email requires a transactional email service
