# ADR: Share Token as JWT with `type: share` Claim

**Date:** 2026-06-20
**Status:** Accepted
**Deciders:** Engineering

---

## Context

Guests can generate shareable links to individual photos (REQ-10–13). Each link must:
- Encode `photo_id`, `event_id`, and a 72-hour fixed expiry
- Be tamper-proof (cannot be forged to access a different photo or event)
- Expire automatically without any database lookup
- Not grant event-level guest access (only resolves to a single photo after the recipient authenticates normally)

The codebase already uses signed JWTs for guest session tokens and photographer auth tokens. A `type` discriminator claim (`"guest"` / `"owner"`) prevents cross-use of different token classes.

---

## Decision

Issue share tokens as JWTs signed with the deployment `SECRET_KEY`, discriminated by `"type": "share"`.

Payload:
```json
{
  "type": "share",
  "sub": "<event_id>",
  "photo_id": "<photo_id>",
  "exp": <unix timestamp, now + 72 hours>,
  "iat": <unix timestamp>
}
```

Validated by `decode_share_token(token)` which:
1. Verifies the HMAC signature
2. Asserts `type == "share"` — rejects guest or owner tokens used as share tokens and vice versa
3. Checks `exp` — raises `HTTPException(410, "link_expired")` when past; raises `HTTPException(403, "invalid_share_token")` for any other failure

A dedicated public endpoint `GET /api/v1/share/{token}` validates the token and returns `{photo_id, event_id, event_slug}`. No guest session token is required.

---

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **JWT `type: share` (selected)** | Reuses existing JWT infrastructure; expiry handled by standard `exp` claim; no new table; tamper-proof via HMAC | JWTs are larger than minimal HMAC payloads (~200 chars); `exp` is fixed at creation (no sliding window — by design) |
| Custom HMAC-signed URL | Smaller token; explicit about what claims are included | Reinvents a subset of JWT; higher risk of subtle implementation bugs (padding, encoding edge cases) |
| Opaque UUID in PostgreSQL `share_links` table | Revocable; auditable; tiny token | DB lookup on every link open; new table + migration; revocation not required by any acceptance criterion |

---

## Consequences

- `create_share_token(photo_id, event_id) → str` and `decode_share_token(token) → dict` are added to `app/services/guest_auth.py`.
- The JWT `type` taxonomy now has three values: `"guest"`, `"owner"`, `"share"`. All future JWT-based features must use a distinct `type` value and validate it explicitly — accepting tokens without checking `type` is a security defect.
- Share tokens must never be accepted where guest tokens are expected, and vice versa. The `get_validated_guest_event` dependency already validates `type == "guest"` — no change needed there.
- `APP_HOST` env var is required on the backend to construct the full `share_url` in the `POST /share` response, so the frontend never needs to know the token structure.
- 72-hour expiry is fixed at creation time (`exp = iat + 72h`). There is no sliding window. This is intentional — REQ-12 / OQ-4 resolved.

---

## References

- Feature requirements: `docs/features/photo-actions/requirements.md` — REQ-10–13, REQ-17–18
- Feature design: `docs/features/photo-actions/design.md`
- Prior ADR (guest JWT design): `docs/decisions/2026-06-19-guest-session-token-design.md`
