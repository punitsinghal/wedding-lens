# ADR: In-Memory Search Result Cache with TTL Eviction

**Date:** 2026-06-20
**Status:** Accepted
**Deciders:** Engineering

---

## Context

Face recognition search is CPU-bound: detecting a face and running ArcFace embedding takes ~200–800 ms on CPU. A guest commonly hits the search endpoint multiple times in one session (e.g. page reload, navigate away and back). Repeating full pipeline execution for the same selfie bytes in the same session wastes CPU and adds latency.

REQ-16 requires that two different guests uploading the same selfie bytes do not share a cache entry — meaning the cache must be keyed by session, not just by selfie hash.

---

## Decision

Implement a module-level in-memory singleton (`search_cache`) in `app/services/search_cache.py`:

- **Cache key:** `(sid, sha256(selfie_bytes))` — scoped to one guest session
- **Cache value:** `list[SearchResult]` — the already-computed result list
- **TTL:** `settings.FACE_SEARCH_CACHE_TTL_SECONDS` (default 3600 s), checked lazily on `get`
- **Eviction:** passive — expired entries are pruned on every `get` or `set` call; no background thread
- **Singleton:** `search_cache = SearchCache()` at module level, shared for the process lifetime

The cache is checked in `run_search` (before detection) and populated after a successful search. It is also checked in the router before calling `run_search` so the `X-Search-Cache` response header can be set accurately.

---

## Options Considered

| Option | Session scoping | Infra cost | Notes |
|--------|----------------|------------|-------|
| **In-memory singleton (selected)** | Exact (via `sid`) | Zero | Lives only in the process; cleared on restart |
| Redis cache | Exact | Redis dependency | Survives restarts; overkill for single-VM deployment |
| No cache | N/A | Zero | Guests re-run detection on every request — poor UX |
| Cache by `event_id + hash` only | Event-wide | Zero | Violates REQ-16 (cross-session leak) |

---

## Consequences

**Positive:**
- Zero infrastructure cost; no new service dependency.
- Eliminates repeated CPU work within a session for the same selfie.
- TTL eviction bounds memory growth: each entry is at most a few KB of `SearchResult` structs.

**Negative:**
- Cache is not shared across multiple backend workers or processes. On a single-VM deployment this is acceptable; a multi-process deployment (e.g. `uvicorn --workers N`) would have per-worker caches.
- Cache is cleared on process restart. Guests get a cache miss after a deploy.
- Passive eviction means stale entries accumulate until the next `get`/`set`. Under very low traffic this is not a concern; under high traffic with many unique sessions the dict grows proportionally until entries expire.

**Rules for future code:**
- Always call `search_cache.clear()` in test fixtures — the singleton is module-global.
- Do not use `search_cache` for anything other than face search results; create a separate cache class for other use cases.
- If a multi-process deployment is needed in the future, replace `SearchCache` with a Redis-backed implementation implementing the same `.get(sid, hash)` / `.set(sid, hash, results)` interface.

---

## References

- Feature design: `docs/features/face-recognition-search/design.md` — Decision 3
- Feature requirements: `docs/features/face-recognition-search/requirements.md` — REQ-15, REQ-16
- Prior ADR: `docs/decisions/2026-06-20-guest-session-id-claim.md` — session ID scoping
