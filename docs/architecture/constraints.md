# Architectural Constraints: WeddingLens
Last updated: 2026-06-19

<!-- Violations of the rules below are treated as blocking issues in /review and /build. -->

## Rules

1. Face processing must be asynchronous — photo import must never block the upload HTTP response
2. Face embeddings at rest must be encrypted — no plaintext vectors in storage or logs
3. Vector searches must be scoped to a single `event_id` — cross-event data must never leak
4. Frontend talks only to the backend REST API — never directly to Qdrant, PostgreSQL, or storage
5. Backend owns all data stores exclusively — no other service or client connects to them directly
6. Face processing jobs must be idempotent — FastAPI BackgroundTasks can be lost if the process restarts; re-running the same job must not create duplicate face records or embeddings

## Trust Boundaries

| From | May call | Must NOT call |
|------|----------|---------------|
| frontend | backend REST API (`/api/v1/*`) | Qdrant, PostgreSQL, storage directly |
| backend | Qdrant, PostgreSQL, local SSD, InsightFace | Another event's data without an explicit `event_id` scope check |
| face pipeline (BackgroundTask) | InsightFace, Qdrant Cloud (HTTPS), PostgreSQL | Must not make outbound calls to any service other than Qdrant Cloud |
| guests | frontend only | backend directly from browser (all calls must go via frontend) |

## Cross-cutting Standards

- **Auth (guests):** QR code-based event link + optional PIN set by the event owner. No user account creation required — guests are anonymous; identity is not stored.
- **Auth (photographers / event owners):** Email + password. Backend issues a JWT on login; the JWT is sent as a `Bearer` token on all subsequent requests. No OAuth provider dependency.
- **Logging:** Structured JSON logs. Never log face vectors, selfie images, or any PII (names, emails, phone numbers).
- **Error handling:** FastAPI exception handlers return JSON `{"detail": "..."}`. Background task failures must be logged with `event_id` and `photo_id` for retryability. No silent swallowing of errors.
- **API versioning:** `/api/v1/` prefix on all backend routes. Breaking changes require a new version prefix.
