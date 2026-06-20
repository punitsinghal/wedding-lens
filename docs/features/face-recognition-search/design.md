# Face Recognition Search — Design

**Status:** Ready for build
**Author:** Engineering
**Date:** 2026-06-20
**Epic:** [docs/epics/face-recognition-search/EPIC.md](../../epics/face-recognition-search/EPIC.md)
**Requirements:** [requirements.md](./requirements.md)

---

## Problem Statement

Guests need to find all event photos containing their face without browsing thousands of images. The backend must accept a selfie, extract a face embedding, search Qdrant for matching faces in the guest's event, and return a ranked list of photos — all within 5 seconds, with no selfie data retained after the request.

---

## Decisions

### Decision 1: Endpoint URL — `POST /api/v1/events/{event_id}/search`

The endpoint follows the existing `get_validated_guest_event(event_id, ...)` dependency pattern: the path `event_id` is cross-checked against the guest JWT's `sub` claim inside the dependency. No `event_id` from the request body is ever used for scoping (REQ-18).

Alternative considered: `POST /api/v1/search` (no path `event_id`, purely token-derived). Rejected because it would require a new variant of `get_validated_guest_event` that does not take a path parameter — unnecessary added complexity.

### Decision 2: Result cache — in-memory, keyed by `(sid, sha256(selfie_bytes))`

The 1-hour result cache (REQ-15/REQ-16) requires per-session scoping. Guest JWTs are stateless and refreshed on every response (new `jti`, new `exp`). To provide a stable session identity across refreshes, a `sid` claim (UUID, generated at login, passed through unchanged on every token refresh) is added to guest JWTs.

Cache key: `(sid, sha256(selfie_bytes))`. TTL: 1 hour from original search time. Cache is in-process (consistent with the existing `GuestRateLimiter` singleton). Lost on server restart — acceptable for MVP.

See ADR: [2026-06-20-guest-session-id-claim.md](../../decisions/2026-06-20-guest-session-id-claim.md).

---

## Request Flow

```mermaid
sequenceDiagram
    participant G as Guest
    participant FE as Frontend
    participant BE as FastAPI /search
    participant IF as InsightFace
    participant QD as Qdrant Cloud
    participant PG as PostgreSQL

    G->>FE: Upload selfie (JPEG/PNG ≤ 20 MB)
    FE->>BE: POST /api/v1/events/{event_id}/search\nmultipart selfie field\nAuthorization: Bearer <guest_token>
    BE->>BE: get_validated_guest_event → extract event_id, sid from token
    BE->>BE: Read selfie bytes into memory; close UploadFile (temp file deleted)
    BE->>BE: sha256(selfie_bytes) → check cache(sid, hash)
    alt Cache hit (created ≤ 1 hour ago)
        BE-->>FE: 200 {results: [...], X-Search-Cache: hit}\nX-Guest-Token: <refreshed>
    else Cache miss
        BE->>IF: _detect_faces(selfie_bytes)
        BE->>BE: del selfie_bytes  — bytes explicitly cleared
        alt 0 faces detected
            BE-->>FE: 422 {detail: "no_face_detected"}
        else Multiple faces, gap < 10pp
            BE-->>FE: 422 {detail: "no_dominant_face"}
        end
        BE->>QD: search(collection=event_<id>, vector=embedding,\nlimit=FACE_SEARCH_RESULT_CAP,\nscore_threshold=FACE_SEARCH_SCORE_THRESHOLD)
        QD-->>BE: [{photo_id, score}, ...] (face-level hits)
        BE->>BE: Dedup by photo_id (keep max score per photo)\nSort desc by score\nDrop scores
        BE->>PG: SELECT id, storage_path FROM photos WHERE id IN (...)
        BE->>BE: Build thumbnail URL per photo → store result in cache(sid, hash)
        BE-->>FE: 200 {results: [{photo_id, thumbnail_url}, ...]}\nX-Guest-Token: <refreshed>
    end
```

---

## Backend Design

### New files

#### `app/routers/search.py`

Single endpoint `POST /api/v1/events/{event_id}/search`. Uses `get_validated_guest_event` dependency. Accepts `multipart/form-data` with one field `selfie: UploadFile`. Enforces 20 MB file size limit before reading bytes. Calls `face_search.run_search`. Returns `SearchResponse`.

Adds `X-Guest-Token` (refreshed token) and `X-Search-Cache: hit|miss` response headers.

#### `app/services/face_search.py`

```
run_search(selfie_bytes, event_id, sid, db) -> list[SearchResult]
```

Steps:
1. `faces = _detect_faces(selfie_bytes)` — reuses existing lazy-init singleton
2. Select dominant face:
   - 0 faces → raise `NoFaceDetectedError`
   - 1 face → use it
   - 2+ faces → sort by `det_score` desc; if `faces[0].det_score - faces[1].det_score < 0.10` → raise `NoDominantFaceError`; else use `faces[0]`
3. `del selfie_bytes` immediately after embedding extracted
4. `hits = search_faces(event_id, embedding, score_threshold, limit)` — calls Qdrant
5. Dedup: `{photo_id: max_score}` dict; sort by score desc
6. Fetch `storage_path` for each `photo_id` from PostgreSQL
7. Build thumbnail URLs
8. Return `[SearchResult(photo_id=..., thumbnail_url=...)]`

Does not write the embedding to disk or PostgreSQL — this is a query-only operation.

#### `app/services/search_cache.py`

Module-level singleton `SearchCache`:

```
get(sid: str, selfie_hash: str) -> list[SearchResult] | None
set(sid: str, selfie_hash: str, results: list[SearchResult]) -> None
_evict() -> None  # remove entries older than TTL
```

Backed by `dict[tuple[str, str], (results, created_at)]`. `_evict()` called on every `get` and `set`. No background thread — lazy eviction is sufficient at MVP scale.

### Modified files

#### `app/services/qdrant.py` — add `search_faces`

```python
def search_faces(
    event_id: uuid.UUID,
    embedding: list[float],
    score_threshold: float,
    limit: int,
) -> list[dict]:
    """
    Vector similarity search against the event's Qdrant collection.
    Returns [{photo_id: str, score: float}] ordered by descending score.
    Only hits above score_threshold are returned.
    """
```

Uses `client.search(collection_name=..., query_vector=..., limit=..., score_threshold=...)`. Extracts `photo_id` from `hit.payload`.

#### `app/services/guest_auth.py` — add `sid` to `create_guest_token`

```python
def create_guest_token(event_id: str, ttl: int, sid: str | None = None) -> str:
    sid = sid or str(uuid.uuid4())
    payload = {
        "sub": event_id,
        "type": "guest",
        "sid": sid,   # stable across refreshes
        "jti": str(uuid.uuid4()),
        ...
    }
```

Existing callers (login endpoints) pass no `sid` → new UUID generated. Refresh call in `get_validated_guest_event` passes the decoded `sid` through.

#### `app/dependencies.py` — pass `sid` on refresh

```python
claims = decode_guest_token(token)
sid = claims.get("sid")
refreshed = create_guest_token(str(event_id), ttl=settings.GUEST_SESSION_IDLE_TTL_SECONDS, sid=sid)
return event, refreshed, sid
```

`get_validated_guest_event` return type changes from `tuple[Event, str]` to `tuple[Event, str, str]` (event, refreshed_token, sid).

> **Breaking change note:** All existing routers that use `get_validated_guest_event` must update their destructuring to unpack three values. Current callers: `gallery.py`, `guest_auth.py` (check all).

#### `app/config.py` — three new settings

```python
FACE_SEARCH_SCORE_THRESHOLD: float = 0.4
FACE_SEARCH_RESULT_CAP: int = 50
FACE_SEARCH_CACHE_TTL_SECONDS: int = 3600
```

### API contract

**Request**
```
POST /api/v1/events/{event_id}/search
Authorization: Bearer <guest_token>
Content-Type: multipart/form-data

selfie: <file>  (JPEG or PNG, ≤ 20 MB)
```

**Response — success**
```json
HTTP 200
X-Guest-Token: <refreshed>
X-Search-Cache: miss | hit

{
  "results": [
    {"photo_id": "uuid", "thumbnail_url": "/api/v1/photos/{id}/thumbnail"},
    ...
  ]
}
```

Zero results (`"results": []`) is a valid success response — it means no photos matched above threshold.

**Response — errors**

| HTTP | `detail` | Condition |
|------|----------|-----------|
| 401 | `"Invalid or expired guest token"` | Bad/expired JWT |
| 413 | `"Selfie exceeds 20 MB limit"` | File too large |
| 422 | `"no_face_detected"` | No face found in selfie |
| 422 | `"no_dominant_face"` | Multiple faces, none dominant |

---

## Frontend Design

### Page: `app/events/[eventId]/search/page.tsx`

Entry point for the search flow. Reads `eventId` from the URL; guest token from session. Orchestrates state: `idle → uploading → results | error`.

### Component: `SelfieUpload`

- File input accepting `image/jpeg, image/png`, max 20 MB (client-side pre-check)
- Camera capture via `<input capture="user">` where supported
- Shows loading spinner while request is in flight
- On error, passes error code to parent for `SearchError` display

### Component: `SearchResults`

- Photo grid, one card per photo
- Cards show thumbnail image only — no score, no label
- Ranked order (API order = match rank)
- "No photos found" empty state when `results.length === 0`
- "Try again" button re-renders `SelfieUpload`

### Component: `SearchError`

| Error code | Message shown |
|---|---|
| `no_face_detected` | "We couldn't detect a face in your photo. Please upload a clear selfie showing your face." |
| `no_dominant_face` | "Your selfie contains multiple faces. Please upload a photo that shows only your face." |

Raw error codes and HTTP status codes are never shown.

---

## Selfie Deletion Guarantee

FastAPI's `UploadFile` wraps a `SpooledTemporaryFile`. At 20 MB, the file will spill to disk during upload. The deletion guarantee is achieved by:

1. `selfie_bytes = await selfie.read()` — copy all bytes into memory
2. `await selfie.close()` — closes and deletes the `SpooledTemporaryFile` immediately
3. Embedding extraction runs on `selfie_bytes` (in-memory only)
4. `del selfie_bytes` immediately after `faces = _detect_faces(selfie_bytes)`
5. No selfie data is passed to Qdrant, PostgreSQL, or any logger

This sequence executes before the Qdrant search — REQ-20 is satisfied even when the search fails.

If `_detect_faces` raises, the `except` block in `face_search.run_search` must call `del selfie_bytes` before re-raising — REQ-21.

---

## Constraints Satisfied

| Constraint | How |
|---|---|
| Searches scoped per `event_id` | `event_id` extracted from JWT by `get_validated_guest_event`; used as Qdrant collection name; path `event_id` cross-checked against token |
| Frontend talks only to backend | Frontend POSTs to backend `/search` endpoint only |
| Backend owns all data stores | Qdrant and PG called only from `face_search.py` and `qdrant.py` |
| Embeddings encrypted at rest | Selfie embedding used only in-memory for search; never written to disk or DB |
| Face processing async | N/A — search is synchronous by design (guest is waiting for results) |

---

## Build Tasks

1. **Modify `app/config.py`** — add `FACE_SEARCH_SCORE_THRESHOLD`, `FACE_SEARCH_RESULT_CAP`, `FACE_SEARCH_CACHE_TTL_SECONDS`
2. **Modify `app/services/guest_auth.py`** — add `sid` param to `create_guest_token`; update `decode_guest_token` to return `sid`
3. **Modify `app/dependencies.py`** — extract `sid` from token claims; pass through on refresh; update return type to `tuple[Event, str, str]`
4. **Update all `get_validated_guest_event` callers** — unpack three values (audit `gallery.py`, `guest_auth.py`, any others)
5. **Extend `app/services/qdrant.py`** — add `search_faces(event_id, embedding, score_threshold, limit)`
6. **Create `app/services/search_cache.py`** — in-memory cache singleton with TTL eviction
7. **Create `app/services/face_search.py`** — dominant-face selection, selfie deletion, Qdrant search, dedup, thumbnail URL construction
8. **Create `app/routers/search.py`** — `POST /api/v1/events/{event_id}/search`; wire into `app/main.py`
9. **Frontend: `SelfieUpload`, `SearchResults`, `SearchError` components**
10. **Frontend: search page** — `app/events/[eventId]/search/page.tsx`
11. **Tests (backend)** — mock `_detect_faces`; cover: no face, single face, dominant face selection (gap ≥/< 0.10), cache hit/miss, selfie deletion on error, event scoping, 20 MB limit rejection, 401 on bad token
12. **Tests (frontend)** — upload flow, error state rendering, results grid

---

## Open Questions

None — all functional questions resolved during grooming. The `sid` JWT claim change is the only design decision that touches an existing interface; it is documented in the ADR.
