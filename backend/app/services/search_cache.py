"""In-memory search result cache with TTL eviction."""
from datetime import datetime, timezone

from app.config import settings


class SearchCache:
    def __init__(self):
        self._store: dict[tuple[str, str], tuple[list, datetime]] = {}

    def get(self, sid: str, selfie_hash: str) -> list | None:
        self._evict()
        entry = self._store.get((sid, selfie_hash))
        if entry is None:
            return None
        results, _ = entry
        return results

    def set(self, sid: str, selfie_hash: str, results: list) -> None:
        self._evict()
        self._store[(sid, selfie_hash)] = (results, datetime.now(timezone.utc))

    def _evict(self) -> None:
        now = datetime.now(timezone.utc)
        ttl = settings.FACE_SEARCH_CACHE_TTL_SECONDS
        expired = [
            k for k, (_, created_at) in self._store.items()
            if (now - created_at).total_seconds() > ttl
        ]
        for k in expired:
            del self._store[k]

    def clear(self) -> None:
        """Test helper."""
        self._store.clear()


search_cache = SearchCache()
