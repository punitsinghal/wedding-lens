"""Public share-link resolver — no guest auth required."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.event import Event
from app.services.guest_auth import decode_share_token

router = APIRouter(prefix="/api/v1", tags=["share"])


@router.get("/share/{token}")
async def resolve_share_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        payload = decode_share_token(token)
    except ValueError as exc:
        detail = str(exc)
        status_code = 410 if detail == "link_expired" else 403
        raise HTTPException(status_code=status_code, detail=detail)

    event_id = payload["sub"]
    result = await db.execute(
        select(Event.slug).where(Event.id == uuid.UUID(event_id))
    )
    event_slug = result.scalar_one_or_none()

    return {
        "photo_id": payload["photo_id"],
        "event_id": event_id,
        "event_slug": event_slug,
    }
