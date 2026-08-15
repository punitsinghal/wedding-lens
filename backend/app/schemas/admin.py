"""Pydantic schemas for admin platform endpoints (design D1, D3, D6)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.event import EventOut


class AdminEventListItem(EventOut):
    """EventOut plus the aggregated context fields REQ-1/REQ-2 ask for.

    photo_count / storage_used_bytes / last_activity_at are computed at
    query time (design D1) — not stored columns.
    """

    photo_count: int
    storage_used_bytes: int
    last_activity_at: datetime


class PaginatedAdminEvents(BaseModel):
    items: list[AdminEventListItem]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)


class ProcessingMonitorOut(BaseModel):
    """All 5 real processing_status counts (design D3 — REQ-4a's 4-bucket
    model doesn't have a slot for 'exhausted retries vs still-retryable').
    """

    pending: int
    processing: int
    complete: int
    failed: int
    error: int


class AdminEventDetailOut(AdminEventListItem):
    processing_monitor: ProcessingMonitorOut


class PlatformHealthOut(BaseModel):
    """GET /api/v1/admin/health response (design D6, REQ-7a)."""

    total_events: int
    total_photos: int
    total_storage_bytes: int
    error_rate_24h: float
