"""Pydantic schemas for gallery endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class GalleryPhotoOut(BaseModel):
    id: uuid.UUID
    thumbnail_url: str | None  # None if thumbnail_path is NULL
    is_photographer_choice: bool
    download_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class GalleryListResponse(BaseModel):
    photos: list[GalleryPhotoOut]
    total: int
    limit: int
    offset: int


class AlbumTabOut(BaseModel):
    ceremony_category: str | None  # None for "All"
    label: str
    photo_count: int


class PhotographerChoicePatch(BaseModel):
    is_photographer_choice: bool


class PhotographerChoiceOut(BaseModel):
    is_photographer_choice: bool
