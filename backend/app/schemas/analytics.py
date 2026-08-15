"""Pydantic schemas for event-owner analytics (design D5, REQ-6a)."""

from pydantic import BaseModel


class EventAnalyticsOut(BaseModel):
    total_views: int
    total_downloads: int
    total_searches: int
