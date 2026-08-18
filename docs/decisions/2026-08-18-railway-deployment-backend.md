# ADR: Backend Deployment — Railway.app
Date: 2026-08-18
Status: accepted

## Context

`2026-06-19-single-vm-local-storage-deployment.md` put the entire stack (FastAPI, Next.js, PostgreSQL, Qdrant client) on one self-hosted 4-core/16GB VM under PM2, with photos on a local/USB SSD. Qdrant itself was already externalized to Qdrant Cloud (`2026-06-19-qdrant-cloud-free-tier.md`). We now want the backend hosted on Railway.app instead of a self-managed VM, to drop VM/PM2 operations (patching, PM2 supervision, manual Postgres install) in favor of a managed platform with git-push deploys and a managed Postgres add-on.

The frontend already deploys to Vercel (`frontend/vercel.json`) and is out of scope for this change — only the FastAPI backend and PostgreSQL move to Railway.

## Decision

Deploy the backend as a single Railway service built from `backend/Dockerfile`, with a Railway-managed PostgreSQL plugin. Photo files (`STORAGE_PATH`) and the InsightFace model cache (via `HOME`) live on a Railway Volume mounted on the backend service. Qdrant Cloud is unchanged. The frontend continues to deploy to Vercel and is pointed at the Railway backend's public URL via `NEXT_PUBLIC_API_URL`.

`alembic upgrade head` runs as part of the container's start command (`backend/Dockerfile`), immediately before `uvicorn` starts, since Railway has no separate release-phase hook. Migrations are additive and safe to re-run on every deploy.

`DATABASE_URL` is normalized in `app/config.py` to rewrite a bare `postgres://`/`postgresql://` scheme (what Railway's Postgres plugin injects) to `postgresql+asyncpg://`, since the app's async SQLAlchemy engine requires the asyncpg driver.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Railway (backend + Postgres plugin) — chosen | Managed Postgres, git-push deploys, no OS/PM2 upkeep, per-service logs/metrics | Volume ties the backend to a single instance (no horizontal scaling); less "carry a USB SSD to the venue" portability than the original ADR |
| Stay on single self-hosted VM + PM2 | Already working, full control, USB SSD portability | Manual patching, manual Postgres backups, no managed rollback/observability |
| Full stack on Railway (frontend too) | One platform for everything | Frontend already works well on Vercel's Next.js-native edge deploys; no reason to migrate it |
| Rewrite storage to S3-compatible object storage now | Removes single-instance constraint entirely | Bigger change than the current single-event load profile justifies; deferred until multi-event/SaaS scaling is actually needed |

## Consequences

- **Ops simplified**: No more manual VM patching, PM2 supervision, or self-managed Postgres backups for the backend — Railway handles builds, restarts, and Postgres backups.
- **Volume replaces USB SSD portability**: The "photographer carries a USB SSD to the venue" story from the single-VM ADR no longer applies to the backend; storage is now a Railway Volume. Constraint 5 (backend owns all data stores exclusively) still holds — only the backend service mounts the volume.
- **Single-instance constraint**: A Railway Volume attaches to exactly one service instance, so the backend cannot be horizontally scaled without first moving to object storage. Acceptable for the current single-event load profile (per the original single-VM ADR's rationale); revisit if serving concurrent events becomes a requirement.
- **Cold-start model downloads avoided**: `HOME` is set to the volume mount path so InsightFace's model cache (`~/.insightface`) persists across deploys instead of re-downloading `buffalo_sc` on every redeploy.
- **DATABASE_URL scheme handled generically**: The `postgres://` → `postgresql+asyncpg://` rewrite in `app/config.py` isn't Railway-specific — it makes the backend portable to any provider that injects the Heroku-style bare scheme.
- **Frontend unaffected**: Vercel deployment, `vercel.json`, and CORS (`allow_origins=["*"]`) are unchanged. Only `NEXT_PUBLIC_API_URL` (Vercel) and `FRONTEND_URL` (Railway) need updating to point at each other's public URLs.

## References

- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md` — superseded for the backend by this ADR
- `docs/decisions/2026-06-19-qdrant-cloud-free-tier.md` — unaffected; Qdrant Cloud stays external either way
- `docs/architecture/constraints.md` — rule 5 (backend owns all data stores exclusively)
- `backend/Dockerfile`, `backend/railway.json`, `backend/app/config.py`
