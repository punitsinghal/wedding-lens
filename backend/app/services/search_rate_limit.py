"""Sliding-window rate limiter for the guest face-search endpoint.

Keyed on the JWT `sid` claim (stable per-session UUID, survives token refresh).
In-process dict — resets on backend restart (acceptable fail-open for MVP;
see ADR 2026-06-22-guest-search-in-process-rate-limiter for rationale).

Design rules (ADR 2026-06-22-guest-search-in-process-rate-limiter):
- Limit: SEARCH_RATE_LIMIT_MAX requests per SEARCH_RATE_LIMIT_WINDOW_SECONDS.
- On breach: HTTP 429 + Retry-After header (seconds until the oldest slot exits
  the window, i.e. when the first accepted request will age out).
- Enforced as a FastAPI dependency on the /search route only (not middleware).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from fastapi import Depends, HTTPException, status

from app.config import settings


class SearchRateLimiter:
    """In-process sliding-window rate limiter keyed on `sid`.

    Args:
        max_requests: Maximum allowed requests in the window.
        window_seconds: Duration of the sliding window in seconds.
        clock: Callable returning the current time as a float (seconds since
               epoch). Defaults to ``time.time``. Inject a custom clock in
               tests so they do not need to sleep.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max = (
            max_requests
            if max_requests is not None
            else settings.SEARCH_RATE_LIMIT_MAX
        )
        self._window = (
            window_seconds
            if window_seconds is not None
            else settings.SEARCH_RATE_LIMIT_WINDOW_SECONDS
        )
        self._clock: Callable[[], float] = clock if clock is not None else time.time
        # sid → deque of request timestamps (oldest first)
        self._store: dict[str, deque[float]] = {}

    def _evict_old(self, sid: str, now: float) -> None:
        """Remove timestamps that have aged out of the window."""
        q = self._store.get(sid)
        if q is None:
            return
        cutoff = now - self._window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            del self._store[sid]

    def check_and_record(self, sid: str) -> None:
        """Record a request attempt for *sid*.

        Raises ``RateLimitExceeded`` if the limit is already at capacity.
        """
        now = self._clock()
        self._evict_old(sid, now)

        q = self._store.get(sid)
        if q is None:
            q = deque()
            self._store[sid] = q

        if len(q) >= self._max:
            # Oldest in-window request ages out at: q[0] + window
            retry_after = max(1, int(q[0] + self._window - now) + 1)
            raise RateLimitExceeded(retry_after=retry_after)

        q.append(now)

    def clear_all(self) -> None:
        """Test helper — reset the entire store."""
        self._store.clear()


class RateLimitExceeded(Exception):
    """Raised by SearchRateLimiter when the window is full."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s.")
        self.retry_after = retry_after


# Module-level singleton used by the FastAPI dependency.
search_rate_limiter = SearchRateLimiter()


def make_enforce_rate_limit_dep(validated_guest_dep: object) -> object:
    """Factory that creates the enforce_search_rate_limit dependency.

    Must be called with ``get_validated_guest_event`` from app.dependencies
    at import time in the router, not here, to avoid circular imports.

    FastAPI caches dependency results per request scope. Because the router
    declares both ``Depends(get_validated_guest_event)`` and
    ``Depends(enforce_search_rate_limit)`` (which also Depends on
    ``get_validated_guest_event``), FastAPI calls get_validated_guest_event
    exactly once per request — no double token refresh.
    """
    async def enforce_search_rate_limit(
        guest_event: tuple = Depends(validated_guest_dep),  # type: ignore[arg-type]
    ) -> None:
        """FastAPI dependency — enforces the sliding-window limit on /search.

        On breach: raises HTTP 429 with Retry-After header.
        """
        _event, _refreshed_token, sid = guest_event
        try:
            search_rate_limiter.check_and_record(sid)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
                headers={"Retry-After": str(exc.retry_after)},
            )

    return enforce_search_rate_limit
