# ADR: Chunked Resumable Upload and SSE Progress in Photographer Dashboard Frontend
Date: 2026-06-21
Status: accepted

## Context

The photographer dashboard photos page previously used a simple multipart `POST` to upload files one at a time with no resume capability. The backend was extended to support a four-step chunked upload protocol (initiate / upload chunks / complete) with deduplication and resume, and a Server-Sent Events endpoint for real-time face-processing progress. The frontend needed to implement these patterns consistently so that future dashboard pages can follow the same conventions.

Several non-obvious decisions were made about how to wire these backend contracts into React state:

1. How to model upload item state (queued → hashing → uploading → done/duplicate/error).
2. How to run N files concurrently while keeping chunks sequential within each file.
3. How to subscribe to SSE with automatic reconnect, given that `EventSource` cannot send custom headers and the backend therefore requires `?token=` query auth.
4. How to keep `lib/api.ts` as the single point of contact with the backend while avoiding a monolithic `apiFetch` wrapper for binary payloads and SSE.

## Decision

### Upload orchestrator

Each file goes through six states: `queued → hashing → uploading → done | duplicate | error`. Progress (0–100 %) tracks chunks sent over total chunks for the uploading state, enabling a per-file progress bar.

Three files are uploaded concurrently (matching the backend ADR `2026-06-19-chunked-upload-chunk-size-concurrency.md`). Within each file, chunks are sent sequentially. Failed chunks are retried up to three times with a 1-second delay before the file is marked as error.

File validation (type and 25 MB cap) is enforced client-side before items enter the queue. Oversized files are shown as inline errors and are never sent to the backend.

### Binary chunk upload

`uploadChunk` in `lib/api.ts` sends `bytes.buffer as ArrayBuffer` with `Content-Type: application/octet-stream` via a raw `fetch` call rather than through the JSON-aware `apiFetch` wrapper. This is the same pattern established in `2026-06-20-selfie-upload-raw-fetch.md`.

### SSE subscription

`subscribeProgress` returns a bare `EventSource` instance. The caller (the photos page component) owns the lifecycle: opens on mount, closes on unmount, and reconnects after 60 seconds on error. Token is passed as `?token=` query param because the `EventSource` API does not support custom headers.

The reconnect timer is stored in a `useRef` so it is stable across renders and can be cleared on unmount without stale closures.

### `getAuthToken` re-export

`lib/api.ts` re-exports `getToken` from `lib/auth.ts` as `getAuthToken` so components can import the token from one module (`@/lib/api`) rather than mixing imports from both `@/lib/api` and `@/lib/auth`. This keeps the convention that components only import from `lib/api`.

### Retry button in photo grid

`PhotoCard` gains a `Retry` button visible when `processing_status` is `failed` or `error`. On click it calls `reprocessPhoto` and optimistically sets the status to `pending` in parent state. No loading spinner is shown at grid level to avoid complexity — the SSE panel will reflect the real status within seconds.

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| Chunked upload with per-file concurrency (chosen) | Resume on disconnect; precise progress per file; matches backend design | More state to manage than simple multipart |
| Simple multipart upload (previous) | Trivial implementation | No resume; breaks on large files or unstable mobile networks |
| SSE with bearer token via query param (chosen) | Works with native `EventSource` without a polyfill | Token visible in server access logs; acceptable given the backend enforces JWT expiry |
| WebSocket for progress | Bidirectional — unnecessary here | Extra protocol complexity; CORS setup harder behind proxies |

## Consequences

- Future photographer dashboard pages that need to upload binary data must use the same raw-fetch pattern in `lib/api.ts` with `Content-Type: application/octet-stream`, not FormData.
- The `UploadItem` interface and the six-status state machine are the canonical model for upload queue items across the frontend.
- SSE-based real-time panels must subscribe via `subscribeProgress(eventId, token)` and own reconnect logic in the component, not in `lib/api.ts`.
- The `getAuthToken` re-export from `lib/api.ts` is the canonical way to access the owner JWT in components.

## References

- `docs/decisions/2026-06-19-chunked-upload-chunk-size-concurrency.md`
- `docs/decisions/2026-06-19-upload-progress-sse.md`
- `docs/decisions/2026-06-20-selfie-upload-raw-fetch.md`
- `frontend/lib/api.ts` — `initiateUpload`, `uploadChunk`, `completeUpload`, `subscribeProgress`
- `frontend/app/events/[eventId]/photos/page.tsx`
