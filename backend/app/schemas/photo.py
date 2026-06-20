import uuid

from pydantic import BaseModel


class PhotoUploadResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
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
