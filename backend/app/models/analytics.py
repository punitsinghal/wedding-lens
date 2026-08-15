"""Admin Platform & Analytics models — view/download/search event rows.

Per design D5 (docs/features/admin-platform/design.md): one row per action,
no guest identity, no dedup key — raw counts only. Unlike
`app.models.privacy` (which deliberately uses bare UUID columns with NO FK
so the audit trail survives event purge), these three tables ARE
ForeignKey-linked with ON DELETE CASCADE: they are lifetime-of-the-event
analytics, not a compliance-retention record, so it's correct for them to
disappear when the event is hard-deleted or purged.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ViewEvent(Base):
    """Guest photo-view beacon (S6). Fire-and-forget, no guest identity."""

    __tablename__ = "view_events"
    __table_args__ = (
        Index("ix_view_events_event_id_occurred_at", "event_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DownloadEvent(Base):
    """Download action (S6) — one row per action, not one row per photo.

    A ZIP download of N photos writes exactly ONE row here.
    """

    __tablename__ = "download_events"
    __table_args__ = (
        Index("ix_download_events_event_id_occurred_at", "event_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SearchEvent(Base):
    """Completed face-search request (S6), including cache hits."""

    __tablename__ = "search_events"
    __table_args__ = (
        Index("ix_search_events_event_id_occurred_at", "event_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
