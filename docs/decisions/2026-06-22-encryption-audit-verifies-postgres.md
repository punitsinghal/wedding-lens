# ADR: Encryption Audit Verifies PostgreSQL `embedding_enc`, Not Qdrant

**Date:** 2026-06-22
**Status:** Accepted
**Deciders:** Engineering, Product

---

## Context

The Privacy & Security feature (REQ-24/REQ-25, AC-7a/7b) calls for an internal, admin-only audit
endpoint that returns a boolean confirming face embeddings are encrypted at rest. As **groomed**,
REQ-24 worded this as confirming that "the **Qdrant** collection is configured with payload
encryption enabled."

That premise conflicts with the existing dual-storage decision
(`docs/decisions/2026-06-19-face-embedding-dual-storage.md`):

- Qdrant stores the **plaintext** float32[512] vector **by design** — encrypting the payload would
  make vectors unsearchable (Qdrant scores against raw floats).
- Qdrant Cloud free tier provides only infrastructure-level at-rest encryption, which is **not
  queryable** by the application — there is no API to assert a per-collection "payload encryption
  enabled" flag.
- The actual application-controlled "encrypted at rest" artifact is the PostgreSQL
  `face_records.embedding_enc` column (AES-256-GCM, key via HKDF from `SECRET_KEY`).

An endpoint reporting a Qdrant payload-encryption flag would therefore be either impossible or a
hardcoded/misleading value — undermining the audit's purpose.

---

## Decision

The encryption-audit endpoint verifies the **PostgreSQL `face_records.embedding_enc`** control, not
Qdrant:

- `GET /internal/audit/embedding-encryption` (admin-only, not publicly routable; rejected with 403
  / connection-refused from public network paths per AC-7b).
- Returns `{"embeddings_encrypted": true, ...}` when indexed `face_records` have **non-null,
  decryptable** `embedding_enc` values (a sampled or full decrypt-check using the derived key).
- REQ-24 / AC-7a are **amended** to drop the Qdrant framing and reference the PostgreSQL artifact.

The Qdrant infrastructure-level encryption remains a documented fact (managed by the provider) but
is **not** the signal this endpoint asserts.

---

## Options Considered

| Option | Truthful? | Verifiable in-app? | Notes |
|--------|-----------|--------------------|-------|
| **Audit PG `embedding_enc` (selected)** | Yes | Yes | Checks the real, app-controlled control |
| Report both stores explicitly | Partially | PG yes / Qdrant no | Qdrant field is non-verifiable boilerplate; adds noise |
| Keep Qdrant wording as groomed | No | No | Not feasible on Qdrant Cloud; would hardcode a misleading value |

---

## Consequences

**Positive:**
- The audit returns a signal that reflects the actual encryption guarantee and is verifiable on
  every run by attempting a decrypt with the derived key.
- Aligns the audit with the dual-storage architecture rather than contradicting it.

**Negative:**
- A compliance reviewer expecting "Qdrant is encrypted" must read this ADR to understand why the
  audit targets PostgreSQL instead. The `/privacy` notice and audit docs should state the
  dual-storage posture plainly.
- A full decrypt-check across all `face_records` is O(n); the endpoint should sample or bound the
  scan for large events (implementation detail for /build).

**Convention for future code:**
- "Embeddings encrypted at rest" is asserted against `face_records.embedding_enc`. Any future audit
  or compliance surface must verify that column, not the Qdrant payload.

---

## References
- `docs/decisions/2026-06-19-face-embedding-dual-storage.md`
- `docs/features/privacy-security/requirements.md` — REQ-24, REQ-25, AC-7a, AC-7b
- `docs/features/privacy-security/design.md` — Decision D4
- `docs/architecture/constraints.md` — Rule 2
