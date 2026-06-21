"""Chunked photo upload endpoints for the photographer dashboard."""
import logging
import math
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, get_event_with_photographer_access
from app.models.event import Event
from app.models.photo import Photo
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services.face_pipeline import process_photo

logger = logging.getLogger("weddinglens.uploads")

router = APIRouter(prefix="/api/v1/events/{event_id}/uploads", tags=["uploads"])

CHUNK_SIZE = 2097152  # 2 MB
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Magic bytes for file-type validation
JPEG_MAGIC = b"\xff\xd8"
PNG_MAGIC = b"\x89PNG"


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


class ChunkUploadResponse(BaseModel):
    chunk_index: int
    received: bool


class CompleteUploadRequest(BaseModel):
    album_id: uuid.UUID | None = None


class CompleteUploadResponse(BaseModel):
    photo_id: uuid.UUID


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
        return JSONResponse(
            status_code=200,
            content={
                "session_id": str(dup_session.id),
                "chunk_size_bytes": dup_session.chunk_size_bytes,
                "total_chunks": dup_session.total_chunks,
                "received_chunks": dup_session.received_chunks or [],
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

    # Create upload session
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
    )
    db.add(session)
    await db.commit()

    # Create tmp directory for chunks
    tmp_dir = Path(settings.STORAGE_PATH) / "tmp" / str(session.id)
    tmp_dir.mkdir(parents=True, exist_ok=True)

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

    return SessionStatusResponse(
        session_id=session.id,
        received_chunks=session.received_chunks or [],
        total_chunks=session.total_chunks,
        status=session.status,
    )


@router.put("/{session_id}/chunks/{chunk_index}", response_model=ChunkUploadResponse)
async def upload_chunk(
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    chunk_index: int,
    request: Request,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> ChunkUploadResponse:
    """Upload a single chunk. Idempotent — returns 200 if chunk already received."""
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

    # Idempotency: already received
    received = session.received_chunks or []
    if chunk_index in received:
        return ChunkUploadResponse(chunk_index=chunk_index, received=True)

    # Write chunk bytes to disk
    chunk_bytes = await request.body()
    chunk_dir = Path(settings.STORAGE_PATH) / "tmp" / str(session_id)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"{chunk_index}.bin"
    chunk_path.write_bytes(chunk_bytes)

    # Update received_chunks — load, append, write back (works on both PostgreSQL and SQLite)
    new_chunks = list(received) + [chunk_index]
    await db.execute(
        sa_update(UploadSession)
        .where(UploadSession.id == session_id)
        .values(
            received_chunks=new_chunks,
            updated_at=datetime.now(timezone.utc),
        )
    )
    # Commit immediately so other processes can see the chunk list
    await db.commit()

    return ChunkUploadResponse(chunk_index=chunk_index, received=True)


@router.post("/{session_id}/complete", status_code=status.HTTP_201_CREATED)
async def complete_upload(
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    body: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
    event: Event = Depends(get_event_with_photographer_access),
    db: AsyncSession = Depends(get_db),
) -> CompleteUploadResponse:
    """Finalize chunked upload: assemble file, insert Photo record, enqueue processing."""
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

    received = session.received_chunks or []
    if len(received) < session.total_chunks:
        missing = [i for i in range(session.total_chunks) if i not in received]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing chunks: {missing}",
        )

    # Determine file extension
    ext = Path(session.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"

    # Generate final photo path
    photo_id = uuid.uuid4()
    final_rel = f"events/{event_id}/{photo_id}{ext}"
    final_abs = Path(settings.STORAGE_PATH) / final_rel
    final_abs.parent.mkdir(parents=True, exist_ok=True)

    # Stream-assemble chunks
    tmp_dir = Path(settings.STORAGE_PATH) / "tmp" / str(session_id)
    with open(final_abs, "wb") as out:
        for i in range(session.total_chunks):
            chunk_path = tmp_dir / f"{i}.bin"
            with open(chunk_path, "rb") as src:
                shutil.copyfileobj(src, out, length=CHUNK_SIZE)

    # Clean up temp dir
    try:
        shutil.rmtree(tmp_dir)
    except Exception as exc:
        logger.warning(
            '{"event": "upload_tmp_cleanup_failed", "session_id": "%s", "error": "%s"}',
            session_id,
            str(exc),
        )

    # Validate assembled file magic bytes
    with open(final_abs, "rb") as f:
        header = f.read(8)
    is_jpeg = header[:2] == JPEG_MAGIC
    is_png = header[:4] == PNG_MAGIC
    if not is_jpeg and not is_png:
        final_abs.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assembled file is not a valid JPEG or PNG",
        )

    # Insert Photo record
    photo = Photo(
        id=photo_id,
        event_id=event_id,
        album_id=body.album_id,
        filename=session.filename,
        storage_path=final_rel,
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
