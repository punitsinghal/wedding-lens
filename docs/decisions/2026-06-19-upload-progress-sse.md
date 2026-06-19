# ADR: Upload Progress Monitoring via Server-Sent Events
Date: 2026-06-19
Status: accepted

## Context

The photographer dashboard must display face-processing progress (total / indexed / pending / failed) that updates within 5 seconds of a photo being indexed, without a full page reload. Three approaches were considered: client polling, Server-Sent Events (SSE), and WebSocket.

## Decision

Use **Server-Sent Events (SSE)** via a `GET /api/v1/events/{event_id}/progress` endpoint that streams `text/event-stream` responses. The backend polls PostgreSQL every 2 seconds internally and emits a `progress` event on each poll. When `pending = 0` and `failed = 0`, it emits a `gallery_ready` event and closes the stream.

## Options Considered

| Option | Mechanism | Assessment |
|--------|-----------|------------|
| A — chosen | SSE (server push, HTTP/1.1) | One-way push; natively supported in FastAPI via `StreamingResponse`; no new protocol or dependency; works through standard HTTP proxies; ~2–4s update lag well within the 5s SLA |
| B | Client polling every 2s | Simpler; equivalent lag; but generates a new HTTP connection every 2 seconds per open dashboard tab — multiplied across events |
| C | WebSocket | Bidirectional — not needed here; requires `ws://` scheme; harder to reverse-proxy; higher implementation complexity for no benefit |

## Consequences

- The SSE handler opens one persistent HTTP connection per dashboard tab for the duration of the upload session. On the single VM, this is not a concern at expected photographer concurrency (1–5 simultaneous users).
- The backend's SSE handler polls PostgreSQL every 2 seconds. This adds a small, bounded read load (one aggregation query per open connection per 2 seconds).
- There is no in-memory pub/sub between BackgroundTasks and the SSE handler; the DB is the source of truth. This keeps the design simple and stateless per process restart.
- Clients must handle automatic SSE reconnection (`EventSource` does this natively in browsers). A suggested server-side connection timeout of 60 seconds is documented as an open question.
- If the platform later adds a WebSocket requirement elsewhere (e.g. live guest feed), SSE and WebSocket can coexist — this decision does not foreclose that option.

## References

- `docs/features/photographer-dashboard/requirements.md` — REQ-10, REQ-11, REQ-12, REQ-13
- `docs/features/photographer-dashboard/design.md`
