"""Guest photo upload endpoint — REQ-1..REQ-24, docs/features/guest-uploads."""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_validated_guest_event
from app.models.photo import Photo
from app.routers.photos import ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE
from app.schemas.photo import PhotoUploadResponse
from app.services.face_pipeline import process_photo
from app.services.guest_auth import guest_upload_rate_limiter, upload_counter
from app.services.image_format import is_allowed_upload_format
from app.services.search_rate_limit import RateLimitExceeded

router = APIRouter(prefix="/api/v1/events/{event_id}/guest-uploads", tags=["guest-uploads"])

MAX_DISPLAY_NAME_LENGTH = 100


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_guest_photo(
    event_id: uuid.UUID,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    display_name: str | None = Form(None),
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoUploadResponse:
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    ip = _get_client_ip(request)
    try:
        guest_upload_rate_limiter.check_and_record(f"{event_id}:{ip}")
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(exc.retry_after)},
        )

    if event.guest_uploads_enabled is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest uploads are disabled for this event.",
        )

    if not upload_counter.has_capacity(str(event_id), sid):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload limit reached for this session.",
        )

    # Content-Type header check is defense-in-depth only — it's client-supplied
    # and trivially spoofable. The magic-byte sniff below is the authoritative
    # gate (see app/services/image_format.py).
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Only JPEG and PNG files are accepted")

    contents = await file.read()
    if not is_allowed_upload_format(contents):
        raise HTTPException(status_code=422, detail="Only JPEG and PNG files are accepted")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds the 25 MB limit")

    if display_name is not None and len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail="Display name must be 100 characters or fewer.",
        )

    photo_id = uuid.uuid4()
    relative_path = f"events/{event_id}/{photo_id}_{file.filename}"
    abs_path = Path(settings.STORAGE_PATH) / relative_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(contents)

    photo = Photo(
        id=photo_id,
        event_id=event_id,
        album_id=None,
        filename=file.filename or "upload",
        storage_path=relative_path,
        file_size=len(contents),
        processing_status="pending",
        uploaded_by="guest",
        guest_display_name=display_name or None,
    )
    db.add(photo)
    await db.commit()

    upload_counter.increment(str(event_id), sid)

    background_tasks.add_task(process_photo, photo_id, event_id)

    return PhotoUploadResponse(
        id=photo.id,
        event_id=photo.event_id,
        album_id=photo.album_id,
        filename=photo.filename,
        processing_status=photo.processing_status,
    )
