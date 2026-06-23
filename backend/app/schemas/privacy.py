"""Pydantic schemas for Privacy & Security endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class RemovalRequestCreate(BaseModel):
    """Payload for guest submitting a face-data removal request (REQ-10)."""

    name: str
    email: EmailStr
    description: str


class RemovalRequestOut(BaseModel):
    """Response schema for a single removal request."""

    id: uuid.UUID
    event_id: uuid.UUID
    submitted_at: datetime
    guest_name: str
    guest_email: str
    description: str
    status: str
    fulfilled_at: datetime | None

    model_config = {"from_attributes": True}


class RemovalRequestSubmittedOut(BaseModel):
    """Response returned to the guest after submission (AC-3b)."""

    id: uuid.UUID
    status: str
    message: str


class RemovalRequestListOut(BaseModel):
    """Paginated list of removal requests for admin (D6)."""

    items: list[RemovalRequestOut]
    pending_count: int
