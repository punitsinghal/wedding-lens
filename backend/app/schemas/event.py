import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

ACCESS_MODES = ("access-code", "magic-link-otp", "public")
STATUSES = ("draft", "published", "suspended", "deleted")


class EventCreate(BaseModel):
    name: str
    bride_name: str
    groom_name: str
    event_date: date | None = None
    slug: str | None = None
    access_mode: str = "public"
    access_code: str | None = None

    @field_validator("access_mode")
    @classmethod
    def validate_access_mode(cls, v: str) -> str:
        if v not in ACCESS_MODES:
            raise ValueError(f"access_mode must be one of {ACCESS_MODES}")
        return v


class EventUpdate(BaseModel):
    name: str | None = None
    bride_name: str | None = None
    groom_name: str | None = None
    event_date: date | None = None
    slug: str | None = None
    cover_photo_id: uuid.UUID | None = None
    access_mode: str | None = None
    access_code: str | None = None

    @field_validator("access_mode")
    @classmethod
    def validate_access_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in ACCESS_MODES:
            raise ValueError(f"access_mode must be one of {ACCESS_MODES}")
        return v


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    bride_name: str
    groom_name: str
    event_date: date | None
    slug: str
    cover_photo_id: uuid.UUID | None
    access_mode: str
    access_code: str | None
    status: str
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SlugConflictError(BaseModel):
    detail: str = "slug_taken"
    suggestions: list[str]


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)
