"""Pydantic schemas for face recognition search."""
from pydantic import BaseModel


class SearchResultOut(BaseModel):
    photo_id: str
    thumbnail_url: str


class SearchResponse(BaseModel):
    results: list[SearchResultOut]
