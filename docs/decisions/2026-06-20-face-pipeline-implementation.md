# ADR: Face Pipeline Implementation Patterns
Date: 2026-06-20
Status: accepted

## Context

The face processing pipeline must detect faces in uploaded photos, generate ArcFace embeddings, encrypt them at rest, and store them in both PostgreSQL (metadata) and Qdrant (vectors). Three design decisions arose during implementation that affect how future pipeline code must be written:

1. InsightFace is a large optional dependency (~500 MB of models) that is not installed in the dev venv and must not be required just to run tests.
2. The pipeline's DB work spans two logical phases (idempotency gate + actual processing), and keeping them in one long transaction risks phantom reads and lock contention under concurrent workers.
3. Error handling in the pipeline needs a clean separation between the happy path and the failure path so that status transitions are reliable even when the exception occurs mid-pipeline.

## Decision

### Lazy import pattern for InsightFace

`_get_face_app()` is a module-level singleton initialiser that performs the `import insightface` only on first call. Tests monkeypatch `app.services.face_pipeline._get_face_app` before any call reaches it, so the package never needs to be importable at test time. This is the only safe way to keep InsightFace out of the dev venv while retaining full unit test coverage.

Rule: Any code that imports a heavy optional dependency (InsightFace, OpenCV, ONNX Runtime) **must** be inside a lazy-init function or inside an `if TYPE_CHECKING` guard, never at module top level.

### Dual-session pattern in `process_photo`

`process_photo` opens and closes a session for the idempotency gate (the atomic `UPDATE ... RETURNING` that transitions `pending/failed → processing`), commits, and only then calls `_run_pipeline` in a new context. The pipeline itself opens further sessions as needed.

This keeps transactions short. The idempotency gate session commits immediately after claiming the job; no session is held across the (potentially slow) image I/O and InsightFace inference. A long-lived session holding a row lock would block retry jobs and concurrent uploads.

Rule: Do not hold an `AsyncSession` open across any I/O that is not a DB call (file reads, network calls, model inference).

### `_run_pipeline` separation for clean error handling

`process_photo` contains only the idempotency gate. All detection, embedding, and storage work lives in `_run_pipeline`. The separation makes two things easier:

- Tests can call `_run_pipeline` directly to exercise the happy and error paths without going through the gate.
- The `except` block in `_run_pipeline` always knows `attempts` (read at the top of the function) and can decide between `failed` (retryable, attempts < 5) and `error` (permanent, attempts ≥ 5) without a separate DB round-trip.

`_run_pipeline` reads `storage_path` and `processing_attempts` from the DB in a single session that is closed before the file read, avoiding a session held across file I/O.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Top-level `import insightface` | Simpler code | Breaks test import; forces InsightFace in dev venv |
| Lazy init via `_get_face_app()` | Monkeypatchable; no dep in dev venv | Slightly non-obvious singleton pattern |
| Single long session for full pipeline | Fewer session objects | Holds lock across file I/O and model inference; blocks retries |
| Dual-session (gate + pipeline) | Short transactions; safe under concurrency | Two session open/close cycles per job |
| Inline error handling in `process_photo` | Fewer functions | Gate and pipeline code interleaved; hard to test error paths in isolation |
| `_run_pipeline` as separate function | Clean error handling; directly testable | One extra indirection |

## Consequences

- Tests must always mock `app.services.face_pipeline._get_face_app` (or `_detect_faces`) — they cannot call the real function without InsightFace installed.
- Future pipeline stages (e.g. thumbnail generation, EXIF extraction) should follow the same dual-session pattern: claim work in a short session, close it, do slow I/O, open a new session to write results.
- `processing_attempts` is read once at the start of `_run_pipeline` and used in the `except` block. If a future refactor re-reads attempts inside the except, ensure it still uses a fresh session (the outer session is closed by that point).

## References

- Epic spec: `docs/architecture/system.md` — face processing pipeline constraints
- ADR: `docs/decisions/2026-06-19-face-embedding-dual-storage.md` — why embeddings are stored in both Qdrant and PostgreSQL
- Implementation: `backend/app/services/face_pipeline.py`, `backend/app/services/retry.py`
