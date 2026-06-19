"""Guest authentication endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.guest_auth import GuestAuthRequest, GuestTokenOut
from app.services import events as event_svc
from app.services.guest_auth import create_guest_token, rate_limiter
from app.config import settings

router = APIRouter(prefix="/api/v1/events", tags=["guest-auth"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/{event_id}/guest-auth", response_model=GuestTokenOut)
async def guest_auth(
    event_id: uuid.UUID,
    data: GuestAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GuestTokenOut:
    """Issue a guest session token for an event after verifying the access code or OTP."""
    event = await event_svc.get_event(db, event_id)
    if event is None or event.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.status not in ("published",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This event is not currently available.",
        )

    if not event.guest_access_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest access has been revoked for this event.",
        )

    ip = _get_client_ip(request)

    if rate_limiter.is_locked_out(str(event_id), ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again in 15 minutes.",
        )

    if event.access_mode == "access-code":
        if not event.access_code or data.code.strip().lower() != event.access_code.lower():
            rate_limiter.record_failure(str(event_id), ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect access code.",
            )
    elif event.access_mode == "magic-link-otp":
        if not event.otp_code or data.code.strip() != event.otp_code:
            rate_limiter.record_failure(str(event_id), ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect OTP code.",
            )
    elif event.access_mode == "public":
        # Public events issue tokens without code validation
        pass

    rate_limiter.reset(str(event_id), ip)
    token = create_guest_token(str(event_id), ttl=settings.GUEST_SESSION_IDLE_TTL_SECONDS)
    return GuestTokenOut(access_token=token)


@router.post("/{event_id}/revoke-guest-access", response_model=dict)
async def revoke_guest_access(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Revoke all active guest sessions for an event (owner only)."""
    from datetime import datetime, timezone
    from app.routers.events import _assert_not_deleted, _assert_owner

    event = await event_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    _assert_not_deleted(event)
    _assert_owner(event, current_user)

    event.guest_access_enabled = False
    event.guest_access_revoked_at = datetime.now(timezone.utc)
    db.add(event)
    await db.flush()
    return {"detail": "Guest access revoked."}


@router.post("/{event_id}/enable-guest-access", response_model=dict)
async def enable_guest_access(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Re-enable guest access for an event after revocation (owner only)."""
    from app.routers.events import _assert_not_deleted, _assert_owner

    event = await event_svc.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    _assert_not_deleted(event)
    _assert_owner(event, current_user)

    event.guest_access_enabled = True
    db.add(event)
    await db.flush()
    return {"detail": "Guest access enabled."}
