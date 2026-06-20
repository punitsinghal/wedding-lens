import uuid
from datetime import datetime

from pydantic import BaseModel


class PhotoUploadResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    album_id: uuid.UUID | None
    filename: str
    processing_status: str


class ProcessingStatusCounts(BaseModel):
    pending: int = 0
    processing: int = 0
    complete: int = 0
    failed: int = 0
    error: int = 0


class FaceProcessingStatusResponse(BaseModel):
    event_id: uuid.UUID
    total_photos: int
    by_status: ProcessingStatusCounts


class PhotoOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    album_id: uuid.UUID | None
    filename: str
    processing_status: str
    thumbnail_url: str | None
    created_at: datetime


class PhotoListResponse(BaseModel):
    items: list[PhotoOut]
    total: int
    limit: int
    offset: int


class PhotoAlbumPatch(BaseModel):
    album_id: uuid.UUID | None = None
