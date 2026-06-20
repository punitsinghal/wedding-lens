# ADR: Stable Session ID (`sid`) Claim in Guest JWTs

**Date:** 2026-06-20
**Status:** Accepted
**Deciders:** Engineering

---

## Context

The face recognition search cache must be scoped per guest session (REQ-16): two different guests uploading the same selfie bytes must not share a cache entry. The cache key is `(session_id, sha256(selfie_bytes))`.

Guest JWTs use a sliding-window idle expiry: every authenticated response issues a refreshed token with a new `exp` and a new `jti`. There is no stable per-session identifier in the current token design. Without one, the cache cannot be scoped to a session across multiple requests.

---

## Decision

Add a `sid` (session ID) claim to guest JWTs:

- Generated as a random UUID v4 at login time (first `create_guest_token` call for a session)
- Passed through unchanged on every subsequent token refresh
- Decoded alongside existing claims in `decode_guest_token`
- Returned as the third element of `get_validated_guest_event` → `tuple[Event, str, str]` (event, refreshed_token, sid)

The `sid` is not a revocation handle and is not stored in PostgreSQL. It is opaque to the frontend.

---

## Options Considered

| Option | Session scoping | Infrastructure cost | Notes |
|--------|----------------|---------------------|-------|
| **`sid` JWT claim (selected)** | Exact | Zero | Claim survives refresh; no new table |
| Cache by `(event_id, selfie_hash)` | Event-wide (not per-session) | Zero | Violates letter of REQ-16; safe in practice |
| PostgreSQL session table with stable `session_id` | Exact | New table + migration | Adds DB round-trip on every authenticated request |

---

## Consequences

**Positive:**
- Cache is correctly scoped per guest session at zero infrastructure cost.
- `sid` can serve as a future revocation handle or analytics correlation key.

**Negative:**
- Any code that calls `create_guest_token` at login time must not pass a `sid` (so a fresh one is generated). Code that calls it at refresh time **must** pass the decoded `sid` through — failing to do so silently breaks cache scoping.
- `get_validated_guest_event` return type changes from `tuple[Event, str]` to `tuple[Event, str, str]`. All existing callers must be updated to unpack three values.

**Rule for future code:**
- Login paths: call `create_guest_token(event_id, ttl)` with no `sid` argument.
- Refresh paths: call `create_guest_token(event_id, ttl, sid=decoded_sid)` — always pass the `sid` extracted from the incoming token.
- Any new dependency that wraps `get_validated_guest_event` must propagate `sid` to callers that need it.

---

## References

- Feature design: `docs/features/face-recognition-search/design.md` — Decision 2
- Feature requirements: `docs/features/face-recognition-search/requirements.md` — REQ-15, REQ-16
- Prior ADR: `docs/decisions/2026-06-19-guest-session-token-design.md` — guest JWT structure
