"""Privacy & Security models — consent records and removal requests.

Per ADR 2026-06-23 (audit-tables-no-fk-survive-purge), event_id and
confirmed_by are bare indexed UUID columns with NO ForeignKey constraint.
This ensures these audit records survive the 30-day event purge job which
calls db.delete(event) with cascade. Do NOT add ForeignKey to these columns.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsentRecord(Base):
    """Records owner consent confirmation at event publish.

    Retained ≥3y independent of event lifecycle (NFR-6).
    Republish creates a new row — no deduplication (AC-1d).
    """

    __tablename__ = "consent_records"
    __table_args__ = (
        # Indexed for admin lookup; no FK — see module docstring.
        Index("ix_consent_records_event_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Bare UUID — no FK — intentionally decoupled from events table (ADR 2026-06-23).
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    # Bare UUID — no FK — the photographer/owner user id.
    confirmed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RemovalRequest(Base):
    """Guest face-data removal requests.

    Never deleted (REQ-16). Retained ≥3y (NFR-6).
    Retained as standalone rows after event purge (ADR 2026-06-23).
    """

    __tablename__ = "removal_requests"
    __table_args__ = (
        # Indexed for admin lookup; no FK — see module docstring.
        Index("ix_removal_requests_event_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Bare UUID — no FK — intentionally decoupled from events table (ADR 2026-06-23).
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    guest_name: Mapped[str] = mapped_column(Text, nullable=False)
    guest_email: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 'pending' | 'fulfilled'
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default=sa.text("'pending'")
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
