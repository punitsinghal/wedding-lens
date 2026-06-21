import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PhotoAlbum(Base):
    """Association object for the photo_albums many-to-many join table."""

    __tablename__ = "photo_albums"

    photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    album_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("albums.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (
        Index("ix_photos_event_status", "event_id", "processing_status"),
        # Gallery indexes are created with DESC expressions in migration 004.
        # Plain Index() here uses ASC but the names match — autogenerate will flag
        # them as different, so keep postgresql_ops overrides if autogenerate is used.
        Index("ix_photos_gallery_all_latest", "event_id", "created_at"),
        Index("ix_photos_gallery_all_popular", "event_id", "download_count"),
        Index("ix_photos_gallery_all_choice", "event_id", "is_photographer_choice", "created_at"),
        Index("ix_photos_gallery_alb_latest", "event_id", "album_id", "created_at"),
        Index("ix_photos_gallery_alb_popular", "event_id", "album_id", "download_count"),
        Index("ix_photos_gallery_alb_choice", "event_id", "album_id", "is_photographer_choice", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("albums.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_photographer_choice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    face_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    face_records: Mapped[list["FaceRecord"]] = relationship(
        "FaceRecord",
        back_populates="photo",
        cascade="all, delete-orphan",
        lazy="select",
    )

    photo_album_entries: Mapped[list["PhotoAlbum"]] = relationship(
        "PhotoAlbum",
        cascade="all, delete-orphan",
        lazy="select",
        foreign_keys=[PhotoAlbum.photo_id],
        primaryjoin="Photo.id == PhotoAlbum.photo_id",
    )


class FaceRecord(Base):
    __tablename__ = "face_records"
    __table_args__ = (
        Index("ix_face_records_event_id", "event_id"),
        Index("ix_face_records_photo_id", "photo_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bbox_x: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_w: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_h: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    photo: Mapped["Photo"] = relationship("Photo", back_populates="face_records", lazy="select")
