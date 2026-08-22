# ADR: Photo Storage Migration to Cloudflare R2
Date: 2026-08-22
Status: accepted

## Context

`2026-06-19-single-vm-local-storage-deployment.md` chose local/USB SSD storage for the single-event load profile, but explicitly flagged that "if the platform later needs to serve multiple concurrent events or offer a SaaS tier, this decision will need revisiting... S3 + managed DB + separate worker is the natural next step." `2026-08-18-railway-deployment-backend.md` moved the backend to Railway with photo storage on a Railway Volume, and again flagged the same constraint: "A Railway Volume attaches to exactly one service instance, so the backend cannot be horizontally scaled without first moving to object storage... revisit if serving concurrent events becomes a requirement."

That requirement has now arrived. On 2026-08-22, the `backend-volume` (provisioned at 500MB) reached 97.7% capacity (488MB used) with three events already coexisting on it, causing `OSError: [Errno 28] No space left on device` on chunk writes during a live upload for event `4e05dc88-ad48-4368-971c-6bbccfdd6632` ("Pratham Software GBM 2026"). Photo data (originals + thumbnails + previews) alone accounted for 392.6MB (78.5%) of the volume across just 270 files. This isn't a one-off fluke — it's the predicted outcome of running multiple concurrent events on a fixed-size, single-instance-attached volume, and it will recur (and worsen) as more events onboard.

Beyond the immediate incident, cost matters here in a way that's easy to miss: PicsLeLo's usage pattern is write-once, read-very-many-times — a photographer uploads once, but every guest re-fetches thumbnails/previews on every gallery view and pulls full-resolution files on download. Railway bills egress (outbound transfer) at $0.05/GB with no free allowance beyond plan credits, so guest-facing read traffic — not storage — is the larger real cost driver as event volume grows. Any storage decision needs to address that, not just the disk-full symptom.

## Decision

Migrate photo file storage — originals, thumbnails (`thumbs/`), previews (`previews/`), and the HEIC→JPEG download-conversion cache (`downloads/`) — from the Railway Volume to Cloudflare R2, an S3-compatible object store.

Reads and writes of photo bytes use presigned URLs issued by the backend, so bytes flow directly between the client (photographer's browser for uploads, guest's browser for gallery/download reads) and R2, rather than proxying through the FastAPI backend. The backend remains the sole issuer of every presigned URL: it authenticates the caller, checks `event_id` ownership/scoping, and only then mints a short-lived, single-object, single-operation (GET or PUT) signed URL. This preserves constraints 3 and 5 (event-scoped isolation, backend owns all data stores) at the authorization layer even though the byte transfer itself doesn't transit the backend process for that one operation.

PostgreSQL (metadata) and Qdrant (embeddings) are unaffected — only file bytes move.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Cloudflare R2 + presigned URLs (chosen) | $0.015/GB-month storage (10x cheaper than Railway's $0.15/GB); $0/GB egress vs. Railway's $0.05/GB — removes the dominant cost driver for a read-heavy photo app; S3-compatible API (portable, mature client libraries); decouples storage from any single compute instance, unblocking horizontal backend scaling; encrypted at rest by default | New external dependency and credentials to manage; presigned URLs are a narrow, deliberate exception to constraint 4's current wording and require that constraint to be amended; adds a moving part to local dev (needs a real bucket or an S3-compatible emulator) |
| Increase Railway Volume size (e.g., 5-10GB) | Zero code change, dashboard-only fix, immediate headroom | Doesn't touch egress cost — the larger driver; volume storage is still 10x R2's per-GB rate and keeps growing linearly with photo count; does nothing for the horizontal-scaling blocker both prior ADRs flagged — defers the same wall instead of removing it |
| AWS S3 + presigned URLs | Same architectural benefits as R2 (S3-compatible, decouples storage from compute); most mature/standard tooling | $0.09/GB egress — worse than even Railway's current $0.05/GB for a download-heavy workload; no cost case for moving at all if egress is the driver |
| R2/S3 but backend-proxied (no presigned URLs, all bytes stream through FastAPI) | Fully preserves constraint 4's literal wording with no client-facing exception | The backend's own egress to guests is still fully billed by Railway ($0.05/GB) since bytes still leave Railway's network per request — this only saves on storage cost and forfeits most of the financial case for migrating; backend also becomes a bandwidth/CPU pass-through for every gallery view and download |

## Consequences

- Storage cost drops ~10x per GB (R2 $0.015/GB-month vs. Railway Volume $0.15/GB-month).
- Egress cost for guest gallery views and downloads drops from $0.05/GB to $0/GB — expected to be the larger saving in absolute terms given the read-heavy usage pattern, and the main reason this migration pays for itself as event volume grows.
- Horizontal scaling of the backend is unblocked: any number of backend instances can read/write the same R2 bucket concurrently, resolving the single-instance constraint flagged in `2026-08-18-railway-deployment-backend.md`. Note this does *not* by itself make the backend horizontally scalable end-to-end — face processing still runs as an in-process `BackgroundTask` on whichever instance received the upload, which remains a separate blocker for true multi-instance operation and is out of scope for this ADR.
- Constraint 4 ("Frontend talks only to the backend REST API — never directly to Qdrant, PostgreSQL, or storage") needs an explicit documented carve-out: direct client access to object storage is permitted only via backend-issued, short-lived, single-object/single-operation signed URLs — all other storage access still goes through the backend API. `docs/architecture/constraints.md` should be updated to state this alongside implementation.
- `docs/architecture/system.md`'s Deployment and Data Stores sections (still describing "Local SSD / USB SSD" and a single VM — not yet updated for the existing Railway deployment either) will need a rewrite to reflect R2 as the photo storage layer once this is implemented.
- New required configuration: an R2 account, bucket, and API credentials (account ID, access key ID, secret access key, bucket name), alongside the existing `DATABASE_URL` / `QDRANT_URL` / `QDRANT_API_KEY`.
- Local development needs a storage strategy — either a real per-developer R2 bucket (free tier covers this comfortably) or an S3-compatible local emulator (e.g., MinIO) — to be decided during implementation, not by this ADR.
- Existing photos on the Railway Volume need a one-time backfill migration to R2 before the volume can be decommissioned. This ADR sets the direction; the migration script/runbook is implementation work.
- No change to constraint 2 (face embeddings encrypted at rest) — that constraint covers embeddings, not raw photo files. R2 encrypts objects at rest by default, matching or exceeding the current local-disk baseline for photo files (which were never separately encrypted).

## References

- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md` — original local-storage decision; explicitly named this migration as the "natural next step" once multi-event/SaaS scaling was needed
- `docs/decisions/2026-08-18-railway-deployment-backend.md` — flagged the single-instance/Volume constraint this ADR resolves
- `docs/architecture/constraints.md` — rule 4 (frontend/backend/storage boundary; needs amendment), rule 5 (backend owns all data stores)
- Incident: `backend-volume` (500MB, Railway) reached 97.7% capacity (488MB used) on 2026-08-22, causing `OSError: [Errno 28] No space left on device` on chunk uploads for event `4e05dc88-ad48-4368-971c-6bbccfdd6632` ("Pratham Software GBM 2026"); photo data (originals + thumbnails + previews) measured at 392.6MB across 270 files at time of incident
- Pricing basis (as of 2026-08-22): Railway Volume $0.15/GB-month storage + $0.05/GB egress; Cloudflare R2 $0.015/GB-month storage + $0/GB egress; AWS S3 $0.09/GB egress
