# ADR: Chunked Upload Session State in PostgreSQL
Date: 2026-06-19
Status: accepted

## Context

Chunked upload requires persisting the set of received chunk indices per file so that a partial upload survives a client disconnect and can be resumed. This state must be readable on reconnect and durable across backend restarts.

## Decision

Store upload session state in a PostgreSQL table (`upload_sessions`). Each row tracks the session metadata and a `received_chunks` integer array that is appended to on each successful chunk acknowledgement.

## Options Considered

| Option | Store | Assessment |
|--------|-------|------------|
| A — chosen | PostgreSQL (`upload_sessions` table) | No new dependency; ACID-safe; queryable for cleanup jobs; consistent with the rest of the data layer; write rate (one UPDATE per chunk) is low and well within PostgreSQL's capacity |
| B | Redis | Faster for high-frequency writes; natural key TTL for auto-cleanup; adds a new service to the single-VM deployment — operational overhead without a clear performance need at this scale |
| C | Filesystem (temp directory) | Simplest to write; no transactions; race conditions on concurrent chunk writes; hard to query for orphaned sessions; cleanup requires filesystem scanning |

## Consequences

- Each chunk acknowledge is an `UPDATE upload_sessions SET received_chunks = array_append(received_chunks, $chunk_index) WHERE id = $session_id`. At 2 MB chunks and 3 concurrent files, peak write rate is well under 10 queries/second.
- Orphaned sessions (`in_progress` older than a configurable threshold) must be cleaned up by a scheduled job. The APScheduler instance already running in-process (see `docs/decisions/2026-06-19-apscheduler-purge-job.md`) is the natural home for this cleanup. Suggested threshold: 24 hours.
- The `received_chunks` array approach avoids the need to track chunk byte offsets explicitly — chunk index is sufficient given the fixed chunk size stored on the session row.
- If chunk size is ever changed, existing in-progress sessions use their stored `chunk_size_bytes` — no migration needed.

## References

- `docs/features/photographer-dashboard/requirements.md` — REQ-6, REQ-7, REQ-8, REQ-9
- `docs/features/photographer-dashboard/design.md`
- `docs/decisions/2026-06-19-apscheduler-purge-job.md`
