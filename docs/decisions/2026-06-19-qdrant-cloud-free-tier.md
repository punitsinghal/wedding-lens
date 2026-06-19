# ADR: Qdrant Vector Database — Cloud Free Tier
Date: 2026-06-19
Status: accepted

## Context

WeddingLens needs a vector database to store and search 512-dim ArcFace face embeddings. The system runs on a single self-hosted VM (see `2026-06-19-single-vm-local-storage-deployment.md`). Two deployment options were considered for Qdrant: running it on the same VM, or using Qdrant Cloud.

## Decision

Use Qdrant Cloud on the free tier. The backend connects to the Qdrant Cloud endpoint over HTTPS using the Qdrant Python client and a cloud API key.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Qdrant Cloud free tier (chosen) | No VM RAM/CPU consumed by Qdrant; zero ops; managed uptime | Face embeddings leave the VM; requires internet during indexing and search; free tier has collection/storage limits |
| Self-hosted Qdrant on VM | Embeddings stay local; no external dependency; works offline | Consumes VM RAM (Qdrant recommends ≥1GB); one more process to manage and restart |

## Consequences

- **Internet required:** The VM must have outbound HTTPS access to Qdrant Cloud during photo indexing and guest face-search requests. A venue with no connectivity will break search.
- **Embeddings leave the VM:** Face embeddings are stored externally on Qdrant Cloud. Embeddings must still be encrypted before storage (constraint 2) to protect biometric data at rest on a third-party service.
- **Free tier limits:** Qdrant Cloud free tier allows 1 cluster with limited storage. Sufficient for a single-event use case; revisit if scaling to multiple concurrent events.
- **Trust boundary updated:** The face processing pipeline is now permitted to make outbound HTTPS calls specifically to Qdrant Cloud. No other outbound calls are permitted.

## References

- `docs/architecture/constraints.md` — Trust Boundaries; Rule 2 (embeddings encrypted at rest)
- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md`
