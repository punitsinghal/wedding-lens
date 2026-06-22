# ADR: In-Process Sliding-Window Rate Limiter for Guest Search, Keyed on `sid`

**Date:** 2026-06-22
**Status:** Accepted
**Deciders:** Engineering

---

## Context

The Privacy & Security feature (REQ-17→20) requires limiting guest selfie-upload and face-search
requests to 10 per 5-minute sliding window, returning HTTP 429 + `Retry-After` on breach, to
prevent enumeration attacks and resource abuse.

Two facts shape the decision:

1. **Selfie-upload and search are the same endpoint** — `POST /api/v1/events/{event_id}/search`
   *is* the selfie-upload path (`backend/app/routers/search.py:17`). The separate `/uploads` router
   is photographer chunked photo upload, not guest selfies. So REQ-17 and REQ-18 collapse to one
   rule on one route. (Confirmed in `docs/wip/analysis-privacy-security-shared-interfaces-2026-06-22.md`.)
2. **A precedent already exists** — `GuestRateLimiter`
   (`backend/app/services/guest_auth.py:56`) is an in-process per-IP lockout for guest code entry.
3. **A stable session key exists** — the `sid` claim in guest JWTs (ADR 2026-06-20) survives token
   refresh and is the natural per-session key.

NFR-4 (as groomed) asked that counters "survive a backend restart" but also listed "in-process
sliding-window" as acceptable — a contradiction, since an in-process structure does not survive
restart. The platform runs on a single VM (`system.md`).

---

## Decision

Implement an **in-process sliding-window rate limiter**, keyed on the JWT `sid` claim, enforced as a
**FastAPI dependency** on the `/search` route:

- Limit: 10 requests / 5-minute sliding window per `sid` (config-driven, mirroring the existing
  `GUEST_LOCKOUT_*` settings pattern).
- On breach: HTTP 429 with a `Retry-After` header (seconds until the window frees a slot).
- Enforced as a route dependency, **not** global middleware — only `/search` is limited and the
  dependency has clean access to the decoded `sid`.
- **NFR-4 is amended:** counters are in-memory and reset on restart (brief fail-open accepted for
  MVP). Redis is the documented upgrade path if a multi-instance deployment is ever introduced.

---

## Options Considered

| Option | New infra | Survives restart | Multi-instance correct | Fit for single-VM MVP |
|--------|-----------|------------------|------------------------|------------------------|
| **In-process sliding window (selected)** | None | No (fail-open) | No | Best — mirrors existing pattern |
| Redis-backed counter | Redis on the VM | Yes | Yes | Heavier; new dependency + ADR + ops |
| Global middleware (in-process) | None | No | No | Rejected: limits all routes, awkward `sid` access |

---

## Consequences

**Positive:**
- Zero new infrastructure; consistent with the existing `GuestRateLimiter` lockout pattern.
- `sid`-keyed limiting is per-session and immune to the IP-sharing problem (NAT, shared Wi-Fi at a
  wedding venue) that per-IP limiting would suffer.
- Dependency scoping keeps the limiter off unrelated routes.

**Negative:**
- Counters reset on backend restart — a guest could briefly exceed the intended rate across a
  restart. Acceptable for an abuse-prevention control on a single VM.
- Not correct across multiple backend instances. The single-VM deployment makes this moot today;
  documented as the trigger to move to Redis.

**Convention for future code:**
- Guest-facing per-session rate limits key on the JWT `sid` claim and live in-process until/unless
  the deployment goes multi-instance.

---

## References
- `docs/decisions/2026-06-20-guest-session-id-claim.md` — the `sid` claim
- `backend/app/services/guest_auth.py:56` — `GuestRateLimiter` precedent
- `docs/wip/analysis-privacy-security-shared-interfaces-2026-06-22.md` — REQ-17 ≡ REQ-18 finding
- `docs/features/privacy-security/requirements.md` — REQ-17→20, NFR-4
- `docs/features/privacy-security/design.md` — Decision D3
