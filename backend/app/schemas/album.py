import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.album import CEREMONY_CATEGORIES


class AlbumCreate(BaseModel):
    name: str
    ceremony_category: str | None = None
    sort_order: int = 0

    @field_validator("ceremony_category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in CEREMONY_CATEGORIES:
            raise ValueError(f"ceremony_category must be one of {CEREMONY_CATEGORIES}")
        return v


class AlbumUpdate(BaseModel):
    name: str | None = None
    ceremony_category: str | None = None
    sort_order: int | None = None
    cover_photo_id: uuid.UUID | None = None

    @field_validator("ceremony_category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in CEREMONY_CATEGORIES:
            raise ValueError(f"ceremony_category must be one of {CEREMONY_CATEGORIES}")
        return v


class AlbumOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    ceremony_category: str | None
    sort_order: int
    cover_photo_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
