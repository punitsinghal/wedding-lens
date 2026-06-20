# ADR: Face Embedding Dual Storage (Qdrant + PostgreSQL)

**Date:** 2026-06-19
**Status:** Accepted (2026-06-19)
**Deciders:** Engineering

---

## Context

NFR-2 of the AI Face Processing epic requires: *"AES-256 encryption must be applied to face embedding vectors before they are stored in Qdrant."*

Applying AES encryption to a float32[512] vector before writing it to Qdrant produces an opaque byte blob. Qdrant computes similarity scores against the raw float vectors — encrypted vectors are not searchable. The requirement as stated is in direct conflict with the search feature.

---

## Decision

Use **dual storage** for face embeddings:

1. **Qdrant Cloud** — store the plaintext float32[512] vector for similarity search. Qdrant Cloud provides at-rest encryption at the infrastructure level (managed service). No application-level encryption is applied before the Qdrant write.

2. **PostgreSQL `face_records.embedding_enc`** — store an AES-256-GCM encrypted copy of the raw embedding bytes. Key derived via HKDF from `SECRET_KEY`. This column is the application-level "encrypted at rest" artifact: it satisfies the spirit of NFR-2 (biometric data is never stored in plaintext outside the search index) while preserving search capability.

---

## Options Considered

| Option | Search works? | App-level encryption? | Notes |
|--------|--------------|----------------------|-------|
| **A: Dual storage (selected)** | Yes | Yes (PG) | Small PG overhead (~2KB/face) |
| B: Encrypt before Qdrant only | No | Yes | Breaks search entirely |
| C: Infrastructure encryption only | Yes | No | No application-layer guarantee |
| D: In-memory FAISS, PG only | Degrades at scale | Yes | Unacceptable search latency above ~50K faces |

---

## Consequences

**Positive:**
- Search works correctly.
- Application-level AES-256-GCM encryption is present in PostgreSQL — satisfies the biometric data protection intent.
- PG copy enables embedding recovery if Qdrant data is lost or corrupted.
- HKDF key derivation allows future key rotation without schema changes.

**Negative:**
- Each face write requires two stores (Qdrant upsert + PG insert).
- `face_records.embedding_enc` adds ~2,076 bytes per face in PostgreSQL. At 100K faces across all events, that is ~200MB — acceptable.
- If plaintext Qdrant vectors are considered insufficient for the "encrypted at rest" requirement by a compliance reviewer, the architecture would need to change to a self-hosted Qdrant with full-disk encryption under operator control.

**Irreversible aspects:**
- Committing to `face_records.embedding_enc` as a BYTEA column is a migration that will contain production biometric data. Changing the encryption scheme later requires a data migration of all existing rows.

---

## References

- [Feature requirements](../features/ai-face-processing/requirements.md) — NFR-2
- [Feature design](../features/ai-face-processing/design.md) — Encryption Scheme section
- [Architecture constraints](../architecture/constraints.md) — Rule 2
