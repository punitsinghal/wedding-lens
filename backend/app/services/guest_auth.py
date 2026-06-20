"""Guest authentication — token issuance, rate limiting, OTP generation."""

import random
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings


def generate_otp_code() -> str:
    """Generate a random 6-character uppercase alphanumeric code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=6))  # noqa: S311


def create_guest_token(event_id: str, ttl: int | None = None, sid: str | None = None) -> str:
    if ttl is None:
        ttl = settings.GUEST_SESSION_IDLE_TTL_SECONDS
    sid = sid or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=ttl)
    payload = {
        "sub": event_id,
        "type": "guest",
        "sid": sid,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_guest_token(token: str) -> dict:
    """Decode and validate a guest JWT. Returns the full payload dict."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
    if payload.get("type") != "guest":
        raise ValueError("Not a guest token")
    if not payload.get("sub"):
        raise ValueError("Token missing sub")
    return payload


@dataclass
class _LockoutEntry:
    count: int = 0
    locked_until: datetime | None = None


class GuestRateLimiter:
    """In-process per-IP lockout for guest code entry attempts."""

    def __init__(
        self,
        max_attempts: int | None = None,
        lockout_seconds: int | None = None,
    ) -> None:
        self._max = max_attempts if max_attempts is not None else settings.GUEST_LOCKOUT_ATTEMPTS
        self._lockout_secs = (
            lockout_seconds if lockout_seconds is not None else settings.GUEST_LOCKOUT_DURATION_SECONDS
        )
        self._store: dict[tuple[str, str], _LockoutEntry] = {}

    def is_locked_out(self, event_id: str, ip: str) -> bool:
        key = (event_id, ip)
        entry = self._store.get(key)
        if not entry or not entry.locked_until:
            return False
        if datetime.now(timezone.utc) >= entry.locked_until:
            del self._store[key]
            return False
        return True

    def record_failure(self, event_id: str, ip: str) -> None:
        key = (event_id, ip)
        entry = self._store.get(key, _LockoutEntry())
        entry.count += 1
        if entry.count >= self._max:
            entry.locked_until = datetime.now(timezone.utc) + timedelta(seconds=self._lockout_secs)
        self._store[key] = entry

    def reset(self, event_id: str, ip: str) -> None:
        self._store.pop((event_id, ip), None)

    def clear_all(self) -> None:
        """Test helper — reset the entire store."""
        self._store.clear()


# Module-level singleton shared by the guest_auth router
rate_limiter = GuestRateLimiter()


def create_share_token(photo_id: str, event_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "share",
        "sub": event_id,
        "photo_id": photo_id,
        "exp": now + timedelta(hours=72),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_share_token(token: str) -> dict:
    """Decode and validate a share JWT. Raises HTTPException on failure."""
    from fastapi import HTTPException
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=410, detail="link_expired")
    except JWTError:
        raise HTTPException(status_code=403, detail="invalid_share_token")
    if payload.get("type") != "share":
        raise HTTPException(status_code=403, detail="invalid_share_token")
    return payload
