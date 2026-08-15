"""Face recognition search endpoint."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_validated_guest_event
from app.schemas.search import SearchResponse, SearchResultOut
from app.services.face_search import NoDominantFaceError, NoFaceDetectedError, run_search
from app.services.search_rate_limit import make_enforce_rate_limit_dep

logger = logging.getLogger("weddinglens")

MAX_SELFIE_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

router = APIRouter(prefix="/api/v1/events/{event_id}", tags=["search"])

# Build the rate-limit dependency here (after get_validated_guest_event is
# defined) to avoid circular imports.  FastAPI will de-dup the shared
# get_validated_guest_event dependency per request — no double token refresh.
_enforce_rate_limit = make_enforce_rate_limit_dep(get_validated_guest_event)


@router.post("/search", response_model=SearchResponse)
async def face_search(
    event_id: uuid.UUID,
    selfie: UploadFile,
    response: Response,
    # D5 — consent_ack: server-enforced precondition (REQ-8a, AC-2e).
    # Must be sent as a multipart form field alongside the selfie.
    # If absent or false → 422 consent_required (AC-2e / design D5).
    consent_ack: bool = Form(...),
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
    # D3 — rate limit dependency (REQ-17/18, ADR 2026-06-22).
    # Uses the same get_validated_guest_event result via FastAPI dep caching.
    _rate_limit: None = Depends(_enforce_rate_limit),
) -> SearchResponse:
    # D5 — Reject if consent affirmation not present (AC-2e).
    if not consent_ack:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="consent_required",
        )

    _event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    # D5 — Emit one structured non-PII audit log line per consented search.
    # Logging constraint (constraints.md): no name, no email, no image, no vector.
    logger.info(
        '{"event": "search_consent_ack", "event_id": "%s", "sid": "%s", "timestamp": "%s"}',
        str(event_id),
        sid,
        datetime.now(timezone.utc).isoformat(),
    )

    if selfie.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unsupported_image_type",
        )

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

    try:
        results, cache_hit = await run_search(selfie_bytes, event_id, sid, db)
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
    finally:
        del selfie_bytes  # drop router's own reference; run_search already drops its own

    response.headers["X-Search-Cache"] = "hit" if cache_hit else "miss"
    return SearchResponse(
        results=[SearchResultOut(photo_id=r.photo_id, thumbnail_url=r.thumbnail_url) for r in results]
    )
