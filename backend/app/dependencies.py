"""FastAPI dependency injection helpers."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth import decode_access_token

bearer_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        user_id_str = decode_access_token(token)
        user_id = uuid.UUID(user_id_str)
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


from app.models.event import Event as EventModel  # noqa: E402


async def get_validated_guest_event(
    event_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[EventModel, str, str]:
    """
    Validate a guest JWT for a specific event.
    Returns (event, refreshed_token, sid).
    The caller should add X-Guest-Token: <refreshed_token> to the response.
    """
    from app.services.guest_auth import decode_guest_token, create_guest_token
    from app.services import events as event_svc
    from app.config import settings

    token = credentials.credentials
    try:
        claims = decode_guest_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired guest token",
        )

    if claims.get("sub") != str(event_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not valid for this event",
        )

    event = await event_svc.get_event(db, event_id)
    if event is None or event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if not event.guest_access_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest access has been revoked",
        )

    # Reject tokens issued before the last revocation
    iat = claims.get("iat")
    if event.guest_access_revoked_at and iat:
        token_iat = datetime.fromtimestamp(iat, tz=timezone.utc)
        if token_iat < event.guest_access_revoked_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session invalidated by access revocation",
            )

    # Tokens issued before the sid claim was introduced get a fresh UUID here.
    # This UUID is NOT stable across refreshes for those old tokens, so their
    # search cache will always miss. Acceptable: old tokens expire naturally.
    sid = claims.get("sid", str(uuid.uuid4()))
    refreshed = create_guest_token(str(event_id), ttl=settings.GUEST_SESSION_IDLE_TTL_SECONDS, sid=sid)
    return event, refreshed, sid
