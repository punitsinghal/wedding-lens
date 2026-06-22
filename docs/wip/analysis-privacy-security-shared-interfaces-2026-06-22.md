## Impact Analysis: Privacy & Security — consent recording on publish + rate limiting on selfie/search
Date: 2026-06-22

Scope: the two parts of the Privacy & Security feature that touch existing shared interfaces.
Everything else in the feature (new `consent_records`/`removal_requests` tables, static
`/privacy` page, removal form, internal audit endpoint, TLS at the proxy) is purely additive
and out of scope for this report.

---

## Change 1 — Record event-owner consent at publish (REQ-3, REQ-4)

**Current form**
- `POST /api/v1/events/{event_id}/publish` — `backend/app/routers/events.py:139`. No request body.
  Auth: `current_user` (photographer JWT). Delegates to `event_svc.publish_event(db, event)`.
- Frontend consumer: `publishEvent(eventId)` — `frontend/lib/api.ts:175` — called from the
  photographer dashboard `frontend/app/events/[eventId]/page.tsx:179`. Single consumer.

**Proposed form**
- On publish, write a `consent_records` row (event_id, timestamp, confirming user identity).
  The confirming identity (`current_user.id`) and timestamp are already available server-side.

**Classification: Non-breaking (owned).**
- The consent record can be written entirely server-side inside `publish_event` using the
  existing `current_user` and server clock — **no change to the request/response contract**.
- The checkbox (REQ-1/REQ-2) is a frontend pre-flight gate only; it does not need to send a new
  field. Republish (REQ-4) already routes through the same publish endpoint, so a second record
  is written automatically.

**Consumers**
| Location | File:line | Classification | Action needed |
|---|---|---|---|
| frontend api client | frontend/lib/api.ts:175 | Owned | None (no contract change) |
| photographer dashboard | frontend/app/events/[eventId]/page.tsx:179 | Owned | Add checkbox gating UI (additive) |

---

## Change 2 — Rate limiting on selfie-upload + face-search (REQ-17, REQ-18, REQ-19, REQ-20)

**Current form**
- `POST /api/v1/events/{event_id}/search` — `backend/app/routers/search.py:17`. Accepts the
  selfie `UploadFile` AND performs the search. **Selfie upload and search are the same endpoint.**
- Frontend consumer: `SelfieUpload.tsx:61` posts the selfie directly via `fetch` (raw, not the
  `apiFetch` wrapper). On `!response.ok` it reads `body.detail` and calls `onError(detail)`.
- Middleware today: **CORS only** (`backend/app/main.py:138`). No rate-limiter exists.
- The separate `/api/v1/events/{event_id}/uploads` router (`uploads.py:25`) is the photographer
  chunked photo upload — NOT the guest selfie path. Out of scope.

**Proposed form**
- Per-guest-session sliding-window limit (10 req / 5 min) on the search endpoint, returning
  HTTP 429 + `Retry-After` when exceeded. Keyed on the guest session token.

**Classification: Non-breaking (owned), with one requirement clarification.**
- Additive: introduces a new 429 response path; existing success contract unchanged.
- **REQ-17 and REQ-18 collapse to a single endpoint and a single rule** in the current
  implementation — there is no separate selfie-upload endpoint. Design should treat this as
  one rate-limited route, not two. (Flag for design + requirements footnote.)
- The existing 429-handling at `frontend/app/g/[slug]/page.tsx:53` is **guest-auth code lockout**,
  not search rate-limiting — it does not cover this path. The `SelfieUpload` error handler needs a
  new 429-specific branch that surfaces `Retry-After` (REQ-20 / AC-5c).

**Consumers**
| Location | File:line | Classification | Action needed |
|---|---|---|---|
| SelfieUpload component | frontend/components/search/SelfieUpload.tsx:61 | Owned | Add 429 + Retry-After branch (additive) |
| guest auth lockout (separate) | frontend/app/g/[slug]/page.tsx:53 | Owned | None — different code path |

---

## Migration path
No migration required. Both changes are non-breaking and shippable atomically within the feature.
New tables are introduced by Alembic migration (additive). No existing consumer breaks.

## Recommendation
**Proceed.** Both shared-interface touches are non-breaking and entirely within owned repos.
Design should resolve two points raised here:
1. Record consent server-side at publish (no contract change) vs. an explicit consent payload.
2. Treat selfie-upload + search as **one** rate-limited endpoint (REQ-17 ≡ REQ-18).

## Open questions
- [ ] Rate-limit store: in-process sliding window vs. Redis (NFR-4 allows either) — owner: Design.
- [ ] Should the search 429 also cover the guest-auth lockout path, or stay separate? — owner: Design.
