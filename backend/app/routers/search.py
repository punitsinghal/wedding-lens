"""Face recognition search endpoint."""
import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_validated_guest_event
from app.schemas.search import SearchResponse, SearchResultOut
from app.services.face_search import NoDominantFaceError, NoFaceDetectedError, run_search
from app.services.search_cache import search_cache

MAX_SELFIE_BYTES = 20 * 1024 * 1024  # 20 MB

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def face_search(
    event_id: uuid.UUID,
    selfie: UploadFile,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    _event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    # Enforce 20 MB limit before reading full bytes
    chunk = await selfie.read(MAX_SELFIE_BYTES + 1)
    if len(chunk) > MAX_SELFIE_BYTES:
        await selfie.close()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Selfie exceeds 20 MB limit",
        )
    selfie_bytes = chunk
    await selfie.close()

    # Check cache before run_search so we can set the header accurately
    selfie_hash = hashlib.sha256(selfie_bytes).hexdigest()
    cache_hit = search_cache.get(sid, selfie_hash) is not None

    try:
        results = await run_search(selfie_bytes, event_id, sid, db)
    except NoFaceDetectedError:
        response.headers["X-Search-Cache"] = "miss"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no_face_detected",
        )
    except NoDominantFaceError:
        response.headers["X-Search-Cache"] = "miss"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no_dominant_face",
        )

    response.headers["X-Search-Cache"] = "hit" if cache_hit else "miss"
    return SearchResponse(
        results=[SearchResultOut(photo_id=r.photo_id, thumbnail_url=r.thumbnail_url) for r in results]
    )
