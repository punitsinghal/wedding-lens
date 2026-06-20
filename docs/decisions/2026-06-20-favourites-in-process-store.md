# ADR: Favourites State via In-Process `FavouritesStore` Singleton

**Date:** 2026-06-20
**Status:** Accepted
**Deciders:** Engineering

---

## Context

Guest favourites must be persisted server-side across page refreshes (REQ-20, REQ-25) and scoped strictly to the guest's session (REQ-21). The guest session design is stateless JWTs — there is no server-side session record in PostgreSQL or Redis. A stable `sid` claim (UUID, generated at login, passed through on every token refresh) is available in every guest JWT as a stable per-session key.

The codebase already has two in-process singletons:
- `GuestRateLimiter` — per-IP attempt counter (read/write, in-process dict)
- `SearchCache` — per-session search result cache (read-only cache)

Favourites introduce a third in-process singleton that is **mutable session state** (not a cache): guests write to it intentionally and expect the data to persist for the life of their session.

---

## Decision

Implement favourites state as a module-level `FavouritesStore` singleton in `app/services/favourites_store.py`.

Internal structure: `dict[sid → (set[photo_id], last_accessed: datetime)]`

Interface:
```python
def get(sid: str) -> set[str]             # returns copy; empty set if no entry
def add(sid: str, photo_id: str) -> None  # idempotent; updates last_accessed
def remove(sid: str, photo_id: str) -> None  # idempotent; updates last_accessed
def _evict() -> None                      # lazy eviction; called on every get/add/remove
```

TTL: entries are evicted when `now - last_accessed > GUEST_SESSION_IDLE_TTL_SECONDS` (24h). This matches the guest JWT sliding window — a guest whose session has expired will have no favourites state on re-authentication, which is the expected behaviour (AC-23).

`last_accessed` is updated (not just on write, but also on read) — sliding TTL, consistent with how the guest JWT sliding window works.

---

## Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **In-process dict (selected)** | Zero infrastructure; zero latency; consistent with existing `SearchCache` / `GuestRateLimiter` pattern; 24h TTL aligns with session window | Lost on server restart; not shared across multiple worker processes if ever horizontally scaled |
| Client-side localStorage | Zero backend changes; survives page refresh naturally | REQ-20 explicitly requires server-side storage; bulk ZIP download (Scenario 9) needs the backend to know the favourites set without the client sending it |
| PostgreSQL `guest_favourites` table | Persists across restarts; works with multiple workers | DB round-trip on every toggle; new table + migration; REQ-20 says "not persisted as a permanent record" — requires a cleanup job |

---

## Consequences

- `FavouritesStore` is a module-level singleton — it is shared across all requests in the same process. Thread safety: `dict` read/write operations in CPython are GIL-protected; `set.add()` and `set.discard()` are atomic. No explicit locking required for MVP at the access patterns expected.
- State loss on server restart is acceptable for MVP on a single VM. If the deployment model changes to multi-worker or multi-process (e.g. `uvicorn --workers N`), `FavouritesStore` will not be shared across workers and must be migrated to a shared store (PostgreSQL or Redis). This is a known future migration point.
- The `PUT /favourites/{photo_id}` and `DELETE /favourites/{photo_id}` endpoints validate that `photo_id` belongs to the guest's `event_id` before touching the store — preventing a guest from adding arbitrary photo IDs to their favourites.
- `GET /favourites` fetches photo metadata from PostgreSQL after reading the `photo_id` set — the store holds only IDs, not photo data.
- Future code that introduces additional per-session mutable state (e.g. a shopping cart, a download queue) should follow this same pattern: a module-level singleton keyed by `sid`, with a TTL matching the session window.

---

## References

- Feature requirements: `docs/features/photo-actions/requirements.md` — REQ-20, REQ-21, REQ-25, REQ-26
- Feature design: `docs/features/photo-actions/design.md`
- Prior ADR (guest session token): `docs/decisions/2026-06-19-guest-session-token-design.md`
- Prior ADR (stable `sid` claim): `docs/decisions/2026-06-20-guest-session-id-claim.md`
- Prior pattern: `app/services/search_cache.py` (read-only in-process cache, same eviction approach)
