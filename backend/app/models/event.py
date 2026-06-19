import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("slug", name="uq_events_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bride_name: Mapped[str] = mapped_column(String(255), nullable=False)
    groom_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # cover_photo_id is intentionally declared without a FK constraint.
    # The `photos` table does not exist in this epic; it will be added in a later
    # epic (Photo Actions / Album Gallery). The column is kept as a plain UUID so
    # that the publish-validation logic (REQ-31) can enforce its presence without
    # requiring a joined table at this stage.
    cover_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # access_mode: "access-code" | "magic-link-otp" | "public"
    access_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="public")
    # access_code is nullable at DB level; app layer enforces presence when
    # access_mode = "access-code"
    access_code: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # status: "draft" | "published" | "suspended" | "deleted"
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="events", lazy="select"
    )
    albums: Mapped[list["Album"]] = relationship(  # noqa: F821
        "Album",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="select",
    )
    slug_redirects: Mapped[list["SlugRedirect"]] = relationship(
        "SlugRedirect",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="select",
    )


class SlugRedirect(Base):
    __tablename__ = "slug_redirects"
    __table_args__ = (UniqueConstraint("old_slug", name="uq_slug_redirects_old_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    old_slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["Event"] = relationship("Event", back_populates="slug_redirects", lazy="select")
