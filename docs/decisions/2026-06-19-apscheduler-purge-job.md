# ADR: Scheduled Purge Job — APScheduler in FastAPI Lifespan
Date: 2026-06-19
Status: accepted

## Context

The Event Management epic requires a 30-day soft-delete grace period. After 30 days, all data for a deleted event must be permanently purged: photos on disk (`STORAGE_PATH`), face embedding vectors in Qdrant Cloud (filtered by `event_id`), and all PostgreSQL records for that event (NFR-3: purge must be consistent — partial deletion is not acceptable).

This is a time-driven operation. It cannot be triggered by a user action. The system runs on a single VM (see ADR `2026-06-19-single-vm-local-storage-deployment.md`) with no external job queue or worker process.

## Decision

Use **APScheduler** (`apscheduler` Python library) registered in the FastAPI `lifespan` context manager to run a daily purge job at 02:00. The job queries PostgreSQL for events with `status = 'deleted'` and `deleted_at < NOW() - 30 days`, then for each: deletes photo files from disk, deletes Qdrant vectors by `event_id` filter, and hard-deletes the event and all cascade records from PostgreSQL.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| APScheduler in FastAPI lifespan (chosen) | Self-contained in backend process; no extra infrastructure; testable via the same test suite; respects "backend owns data stores" constraint | Job is lost if backend process is down at fire time; adds one dependency |
| OS-level cron + standalone script | Runs independently of backend uptime; OS-native reliability | Second process connecting directly to PostgreSQL and Qdrant — violates the spirit of constraint 5 (backend owns data stores exclusively); separate env config to maintain |
| PostgreSQL `pg_cron` | Runs even when backend is down; no extra process | Cannot delete files on disk or call Qdrant — cannot fulfil the full purge requirement without a callback mechanism; not viable as a sole solution |

## Consequences

- The backend gains a dependency on `apscheduler`.
- A missed daily run (backend down at 02:00) is acceptable: the next day's run picks up any event whose `deleted_at` threshold has passed and whose records still exist. The purge is idempotent.
- The purge job must be implemented with per-event error handling: if one event's purge fails (e.g. Qdrant unreachable), the job logs the failure with `event_id` and continues to the next event rather than aborting the entire run.
- A `purge_audit` log (structured JSON, not a DB table) is emitted per run for observability — consistent with the "structured JSON logs" cross-cutting standard.
- If the platform later moves to a multi-process or distributed deployment, the purge job should be migrated to a dedicated worker (Celery, ARQ) to avoid double-firing.

## References

- `docs/features/event-management/requirements.md` — REQ-14, REQ-15, NFR-3
- `docs/features/event-management/design.md` — Decision B
- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md`
- `docs/architecture/constraints.md` — Rule 5 (backend owns data stores exclusively)
