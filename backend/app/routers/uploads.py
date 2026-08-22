"""Chunked photo upload endpoints for the photographer dashboard.

Chunks upload directly to Cloudflare R2 via presigned S3-compatible
multipart-upload URLs — the backend never receives chunk bytes on this
path. See docs/features/photo-storage-migration/design.md ("Chunked
upload (photographer)") and
docs/decisions/2026-08-22-presigned-url-image-delivery.md.
"""
import logging
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_event_with_photographer_access
from app.models.event import Event
from app.models.photo import Photo
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services import r2
from app.services.face_pipeline import process_photo
from app.services.image_format import is_allowed_upload_format

logger = logging.getLogger("weddinglens.uploads")

router = APIRouter(prefix="/api/v1/events/{event_id}/uploads", tags=["uploads"])

# 8 MiB. S3-compatible multipart upload requires every part except the last
# to be >= 5 MiB; the app's chunk size now maps 1:1 onto R2 multipart parts,
# so it must stay comfortably above that floor. See
# docs/features/photo-storage-migration/design.md.
CHUNK_SIZE = 8 * 1024 * 1024
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class InitiateUploadRequest(BaseModel):
    filename: str
    file_size_bytes: int
    content_hash: str


class InitiateUploadResponse(BaseModel):
    session_id: uuid.UUID
    chunk_size_bytes: int
    total_chunks: int


class DuplicateUploadResponse(BaseModel):
    photo_id: uuid.UUID
    status: str  # "duplicate"


class ResumableUploadResponse(BaseModel):
    session_id: uuid.UUID
    chunk_size_bytes: int
    total_chunks: int
    received_chunks: list[int]
    status: str  # "resumable"


class SessionStatusResponse(BaseModel):
    session_id: uuid.UUID
    received_chunks: list[int]
    total_chunks: int
    status: str


class ChunkUploadUrlResponse(BaseModel):
    chunk_index: int
    url: str


class CompleteUploadRequest(BaseModel):
    album_id: uuid.UUID | None = None


class CompleteUploadResponse(BaseModel):
    photo_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _object_key(event_id: uuid.UUID, photo_id: uuid.UUID, filename: str) -> str:
    """Reconstruct the R2 object key for a session — same scheme as before
    the migration: events/{event_id}/{photo_id}{ext}."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    return f"events/{event_id}/{photo_id}{ext}"


def _received_chunk_indices(parts: list[dict]) -> list[int]:
    """Convert 1-indexed R2 PartNumbers to 0-indexed chunk indices."""
    return [part["PartNumber"] - 1 for part in parts]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def initiate_upload(
    event_id: uuid.UUID,
    body: InitiateUploadRequest,
    event: Event = Depends(get_event_with_photographer_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a new chunked upload session. Handles deduplication."""
    # Dedup check 1: photo already exists with this content_hash
    dup_photo_result = await db.execute(
        select(Photo).where(
            Photo.event_id == event_id,
            Photo.content_hash.is_not(None),
            Photo.content_hash == body.content_hash,
        )
    )
    dup_photo = dup_photo_result.scalar_one_or_none()
    if dup_photo is not None:
        return JSONResponse(
            status_code=200,
            content={"photo_id": str(dup_photo.id), "status": "duplicate"},
        )

    # Dedup check 2: in-flight session for same content_hash
    dup_session_result = await db.execute(
        select(UploadSession).where(
            UploadSession.event_id == event_id,
            UploadSession.content_hash == body.content_hash,
            UploadSession.status == "in_progress",
        )
    )
    dup_session = dup_session_result.scalar_one_or_none()
    if dup_session is not None:
        dup_key = _object_key(event_id, dup_session.photo_id, dup_session.filename)
        try:
            parts = r2.list_parts(dup_key, dup_session.r2_upload_id)
        except r2.StorageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is temporarily unavailable. Please try again.",
            ) from exc
        return JSONResponse(
            status_code=200,
            content={
                "session_id": str(dup_session.id),
                "chunk_size_bytes": dup_session.chunk_size_bytes,
                "total_chunks": dup_session.total_chunks,
                "received_chunks": _received_chunk_indices(parts),
                "status": "resumable",
            },
        )

    # Validate file size
    if body.file_size_bytes > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File exceeds the {MAX_FILE_SIZE // (1024*1024)} MB limit",
        )

    # Validate filename extension
    ext = Path(body.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Calculate total chunks
    total_chunks = max(1, math.ceil(body.file_size_bytes / CHUNK_SIZE))

    # Generate the photo id and object key up front so the multipart upload
    # and the (eventual) Photo row agree on the same key.
    photo_id = uuid.uuid4()
    key = f"events/{event_id}/{photo_id}{ext}"

    try:
        r2_upload_id = r2.create_multipart_upload(key)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    # Only create the DB row once the R2 multipart upload actually exists —
    # never let Postgres reference an upload_id that R2 doesn't have.
    session = UploadSession(
        id=uuid.uuid4(),
        event_id=event_id,
        uploader_id=current_user.id,
        filename=body.filename,
        file_size_bytes=body.file_size_bytes,
        content_hash=body.content_hash,
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=total_chunks,
        received_chunks=[],
        status="in_progress",
        photo_id=photo_id,
        r2_upload_id=r2_upload_id,
    )
    db.add(session)
    await db.commit()

    return InitiateUploadResponse(
        session_id=session.id,
        chunk_size_bytes=CHUNK_SIZE,
        total_chunks=total_chunks,
    )


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    event: Event = Depends(get_event_with_photographer_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionStatusResponse:
    """Get session status for upload resume."""
    result = await db.execute(
        select(UploadSession).where(
            UploadSession.id == session_id,
            UploadSession.event_id == event_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")

    # Only the original uploader or the event owner can query
    if session.uploader_id != current_user.id and event.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not the uploader or event owner",
        )

    key = _object_key(event_id, session.photo_id, session.filename)
    try:
        parts = r2.list_parts(key, session.r2_upload_id)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    return SessionStatusResponse(
        session_id=session.id,
        received_chunks=_received_chunk_indices(parts),
        total_chunks=session.total_chunks,
        status=session.status,
    )


@router.get("/{session_id}/chunks/{chunk_index}/url", response_model=ChunkUploadUrlResponse)
async def get_chunk_upload_url(
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    chunk_index: int,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> ChunkUploadUrlResponse:
    """Return a presigned R2 UploadPart URL for one chunk. Pure read + presign —
    no database writes; R2's list_parts is the source of truth for what's
    actually been received (see complete_upload / get_session_status)."""
    result = await db.execute(
        select(UploadSession).where(
            UploadSession.id == session_id,
            UploadSession.event_id == event_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")

    if session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Session is not in_progress (current status: {session.status})",
        )

    if chunk_index >= session.total_chunks or chunk_index < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"chunk_index {chunk_index} out of range (total_chunks={session.total_chunks})",
        )

    key = _object_key(event_id, session.photo_id, session.filename)
    part_number = chunk_index + 1
    try:
        url = r2.generate_upload_part_url(key, session.r2_upload_id, part_number)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    return ChunkUploadUrlResponse(chunk_index=chunk_index, url=url)


@router.post("/{session_id}/complete", status_code=status.HTTP_201_CREATED)
async def complete_upload(
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    body: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> CompleteUploadResponse:
    """Finalize chunked upload: complete the R2 multipart upload, insert the
    Photo record, enqueue processing."""
    result = await db.execute(
        select(UploadSession).where(
            UploadSession.id == session_id,
            UploadSession.event_id == event_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")

    if session.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Session is not in_progress (current status: {session.status})",
        )

    key = _object_key(event_id, session.photo_id, session.filename)

    try:
        parts = r2.list_parts(key, session.r2_upload_id)
    except r2.StorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage service is temporarily unavailable. Please try again.",
        ) from exc

    if len(parts) < session.total_chunks:
        received = _received_chunk_indices(parts)
        missing = [i for i in range(session.total_chunks) if i not in received]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing chunks: {missing}",
        )

    try:
        r2.complete_multipart_upload(key, session.r2_upload_id, parts)

        if not r2.head_object(key):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Upload completed but object not found in storage",
            )

        # Validate assembled file magic bytes — authoritative gate, independent
        # of the filename extension (see app/services/image_format.py).
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
            detail="Assembled file is not a valid JPEG or PNG",
        )

    photo_id = session.photo_id

    # Insert Photo record
    photo = Photo(
        id=photo_id,
        event_id=event_id,
        album_id=body.album_id,
        filename=session.filename,
        storage_path=key,
        file_size=session.file_size_bytes,
        content_hash=session.content_hash,
        processing_status="pending",
    )
    db.add(photo)

    # Mark session complete
    await db.execute(
        sa_update(UploadSession)
        .where(UploadSession.id == session_id)
        .values(status="complete", updated_at=datetime.now(timezone.utc))
    )

    await db.commit()

    # Enqueue face processing (must not block response)
    background_tasks.add_task(process_photo, photo_id, event_id)

    logger.info(
        '{"event": "upload_complete", "session_id": "%s", "photo_id": "%s", "event_id": "%s"}',
        session_id,
        photo_id,
        event_id,
    )

    return CompleteUploadResponse(photo_id=photo_id)
