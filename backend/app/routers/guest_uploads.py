"""Guest photo upload endpoints — REQ-1..REQ-24, docs/features/guest-uploads.

Guests upload directly to Cloudflare R2 via a presigned single-shot PUT URL
instead of sending file bytes through the backend as multipart/form-data.
See docs/features/photo-storage-migration/design.md ("Guest upload / event
cover upload") and docs/decisions/2026-08-22-presigned-url-image-delivery.md.

Two-step flow, mirroring the "backend issues URL -> client PUTs directly ->
backend verifies before writing the DB row" shape used by the chunked
photographer upload flow (app/routers/uploads.py), just without the
multipart machinery since guest uploads are always single-request:

1. POST /initiate  - runs all client-supplied-metadata validation (rate
   limit, capacity, display name, extension, size sanity check), then
   returns a presigned PUT URL. No DB write yet.
2. POST /{photo_id}/complete - after the browser has PUT the bytes to R2,
   verifies the object actually exists and is a real JPEG/PNG by reading it
   back from R2, then writes the Photo row and enqueues face processing.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_validated_guest_event
from app.models.photo import Photo
from app.routers.photos import MAX_FILE_SIZE
from app.schemas.photo import PhotoUploadResponse
from app.services import r2
from app.services.face_pipeline import process_photo
from app.services.guest_auth import guest_upload_rate_limiter, upload_counter
from app.services.image_format import is_allowed_upload_format
from app.services.search_rate_limit import RateLimitExceeded

router = APIRouter(prefix="/api/v1/events/{event_id}/guest-uploads", tags=["guest-uploads"])

MAX_DISPLAY_NAME_LENGTH = 100

# Same allow-list as the photographer chunked-upload flow
# (app/routers/uploads.py) — kept as a literal here rather than imported to
# match this file's existing style of importing shared constants
# (MAX_FILE_SIZE) only from app.routers.photos, not from sibling routers.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _object_key(event_id: uuid.UUID, photo_id: uuid.UUID, filename: str) -> str:
    return f"events/{event_id}/{photo_id}_{filename}"


class InitiateGuestUploadRequest(BaseModel):
    filename: str
    file_size_bytes: int
    display_name: str | None = None


class InitiateGuestUploadResponse(BaseModel):
    photo_id: uuid.UUID
    upload_url: str


class CompleteGuestUploadRequest(BaseModel):
    filename: str
    display_name: str | None = None


@router.post(
    "/initiate",
    response_model=InitiateGuestUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_guest_upload(
    event_id: uuid.UUID,
    body: InitiateGuestUploadRequest,
    request: Request,
    response: Response,
    guest_event: tuple = Depends(get_validated_guest_event),
) -> InitiateGuestUploadResponse:
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

    if body.display_name is not None and len(body.display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail="Display name must be 100 characters or fewer.",
        )

    # Extension check is defense-in-depth only — there are no file bytes to
    # sniff yet at this point. The magic-byte sniff in /complete is the
    # authoritative gate (see app/services/image_format.py).
    ext = Path(body.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Only JPEG and PNG files are accepted")

    # file_size_bytes is client-reported and only defense-in-depth — the
    # real check happens in /complete against R2's actual object size.
    if body.file_size_bytes > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="File exceeds the 25 MB limit")

    photo_id = uuid.uuid4()
    key = _object_key(event_id, photo_id, body.filename)

    try:
        upload_url = r2.generate_put_url(key)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    return InitiateGuestUploadResponse(photo_id=photo_id, upload_url=upload_url)


@router.post(
    "/{photo_id}/complete",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_guest_upload(
    event_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: CompleteGuestUploadRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    guest_event: tuple = Depends(get_validated_guest_event),
    db: AsyncSession = Depends(get_db),
) -> PhotoUploadResponse:
    event, refreshed_token, sid = guest_event
    response.headers["X-Guest-Token"] = refreshed_token

    # Re-checked here (defense in depth) — the event could have been toggled
    # off between /initiate and /complete.
    if event.guest_uploads_enabled is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest uploads are disabled for this event.",
        )

    key = _object_key(event_id, photo_id, body.filename)

    try:
        size = r2.get_object_size(key)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    if size is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload not found or incomplete",
        )

    if size > MAX_FILE_SIZE:
        try:
            r2.delete_object(key)
        except r2.StorageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is temporarily unavailable. Please try again.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File exceeds the 25 MB limit",
        )

    try:
        header = r2.read_range(key, 0, 15)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    if not is_allowed_upload_format(header):
        try:
            r2.delete_object(key)
        except r2.StorageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is temporarily unavailable. Please try again.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only JPEG and PNG files are accepted",
        )

    photo = Photo(
        id=photo_id,
        event_id=event_id,
        album_id=None,
        filename=body.filename,
        storage_path=key,
        file_size=size,
        processing_status="pending",
        uploaded_by="guest",
        guest_display_name=body.display_name or None,
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
