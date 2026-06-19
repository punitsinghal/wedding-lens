# ADR: Chunked Upload — 2 MB Chunks, 3 Concurrent Files
Date: 2026-06-19
Status: accepted

## Context

The photographer dashboard must support batch upload of up to 1,000 JPEG/PNG files (≤ 25 MB each) with automatic resume after network interruption. Two parameters require a decision: the fixed chunk size used to split each file, and the number of files uploaded concurrently from the client.

The platform runs on a single 4-core/16GB VM. Upload, face processing (BackgroundTasks), and all other backend work compete for the same CPU and I/O resources. Choosing too high a concurrency risks starving the face pipeline during upload.

## Decision

- **Chunk size:** 2 MB per chunk
- **Client concurrency:** 3 files uploading simultaneously (each file's chunks uploaded serially within that file)

## Options Considered

| Option | Chunk size | Concurrency | Assessment |
|--------|-----------|-------------|------------|
| A — chosen | 2 MB | 3 files | ~13 chunks per 25 MB file; precise resume granularity; ~6 MB peak in-flight RAM; predictable server load |
| B | 5 MB | 3 files | Fewer HTTP round-trips; more data lost and retransmitted on a disconnect mid-chunk |
| C | 2 MB | 5 files | Faster on large batches with good connectivity; risks saturating the single VM when face BackgroundTasks are also running |

## Consequences

- A 25 MB file requires at most 13 chunk requests. HTTP overhead is negligible at this scale.
- On resume, at most 2 MB of already-received data is retransmitted (one in-flight chunk). This is acceptable.
- The backend chunk assembly (`POST /complete`) must stream chunks from PostgreSQL/SSD sequentially to avoid loading an entire 25 MB file into memory at once.
- The 3-concurrent-file limit is enforced client-side only; the backend does not enforce a per-session concurrency cap. If future clients ignore this, server load must be monitored.
- Chunk size is stored per `upload_session` row; changing the default in future requires only a config change, not a migration.

## References

- `docs/features/photographer-dashboard/requirements.md` — REQ-6, REQ-7, REQ-8, REQ-9
- `docs/features/photographer-dashboard/design.md`
- `docs/decisions/2026-06-19-single-vm-local-storage-deployment.md`
