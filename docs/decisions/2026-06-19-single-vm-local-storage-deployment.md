# ADR: Single-VM Local-Storage Deployment
Date: 2026-06-19
Status: accepted

## Context

WeddingLens is a per-event tool: a photographer uploads photos once, runs indexing once, and guests search during or after the wedding. The load profile is a short burst (indexing) followed by a modest steady-state (guest searches), all within a predictable window tied to a single event.

## Decision

Deploy the entire system — FastAPI backend, Next.js frontend, PostgreSQL, and Qdrant — on a single 4-core/16GB VM. Store photo files on a local SSD or attached USB SSD configured via the `STORAGE_PATH` environment variable.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Single VM + local SSD (chosen) | Simple to operate, low cost, no cloud egress fees, no S3 config, portable (USB SSD) | No redundancy; if the VM dies mid-event, service is down |
| Cloud-native (managed DB, S3, separate worker) | Highly available, scales automatically | Over-engineered for a one-off event; significantly more ops complexity and cost |
| Docker Compose on VM + cloud object storage | Middle ground — managed storage, simple compute | Still requires S3 config; USB SSD is simpler and faster for local access |

## Consequences

- **Simpler**: No cloud credentials, no S3 bucket config, no managed DB — one VM, one deploy.
- **Portable**: USB SSD lets the photographer carry their own storage to the venue and plug it in.
- **No HA**: If the VM restarts during indexing, in-flight BackgroundTasks are lost. This is acceptable because indexing can be re-run (jobs are idempotent — constraint 6).
- **Growth path**: If the platform later needs to serve multiple concurrent events or offer an SaaS tier, this decision will need revisiting via `/arch update` — at that point, S3 + managed DB + separate Celery worker is the natural next step.

## References

- `docs/architecture/constraints.md` — rule 6 (idempotent jobs)
- `docs/architecture/system.md` — Deployment section
