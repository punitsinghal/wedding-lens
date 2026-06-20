"""Public share-link resolver — no guest auth required."""
from fastapi import APIRouter

from app.services.guest_auth import decode_share_token

router = APIRouter(prefix="/api/v1", tags=["share"])


@router.get("/share/{token}")
async def resolve_share_token(token: str) -> dict:
    payload = decode_share_token(token)
    return {
        "photo_id": payload["photo_id"],
        "event_id": payload["sub"],
    }
