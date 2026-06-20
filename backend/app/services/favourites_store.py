"""In-process favourites store — keyed by guest session ID, sliding TTL eviction."""
from datetime import datetime, timezone

from app.config import settings


class FavouritesStore:
    def __init__(self):
        # sid -> (photo_ids: set[str], last_accessed: datetime)
        self._store: dict[str, tuple[set[str], datetime]] = {}

    def get(self, sid: str) -> set[str]:
        self._evict()
        entry = self._store.get(sid)
        if entry is None:
            return set()
        photo_ids, _ = entry
        self._store[sid] = (photo_ids, datetime.now(timezone.utc))  # sliding touch
        return set(photo_ids)  # copy

    def add(self, sid: str, photo_id: str) -> None:
        self._evict()
        photo_ids, _ = self._store.get(sid, (set(), None))
        photo_ids.add(photo_id)
        self._store[sid] = (photo_ids, datetime.now(timezone.utc))

    def remove(self, sid: str, photo_id: str) -> None:
        self._evict()
        entry = self._store.get(sid)
        if entry is None:
            return
        photo_ids, _ = entry
        photo_ids.discard(photo_id)
        self._store[sid] = (photo_ids, datetime.now(timezone.utc))

    def _evict(self) -> None:
        now = datetime.now(timezone.utc)
        ttl = settings.GUEST_SESSION_IDLE_TTL_SECONDS
        expired = [
            sid for sid, (_, last_accessed) in self._store.items()
            if (now - last_accessed).total_seconds() > ttl
        ]
        for sid in expired:
            del self._store[sid]

    def clear(self) -> None:
        """Test helper."""
        self._store.clear()


favourites_store = FavouritesStore()
