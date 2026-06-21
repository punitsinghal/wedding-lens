import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, func, types
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IntListType(types.TypeDecorator):
    """
    A TypeDecorator for a list-of-integers column.

    - In PostgreSQL: delegates to native INTEGER[] (ARRAY). The DDL is created
      by the migration as INTEGER[]; this TypeDecorator handles Python↔DB conversion.
    - In SQLite (test DB): stores as a JSON text string so that Base.metadata.create_all
      works without requiring ARRAY support.

    The `impl = Text` default is used only for SQLite CREATE TABLE in tests.
    For PostgreSQL the migration manages DDL; `load_dialect_impl` returns the real
    ARRAY type so that SQLAlchemy reads/writes correct PostgreSQL values at runtime.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import ARRAY
            return dialect.type_descriptor(ARRAY(Integer))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if dialect.name == "postgresql":
            # Pass the list directly; psycopg2 knows how to handle Python lists for ARRAY
            return value if value is not None else []
        # SQLite: serialize to JSON
        if value is None:
            return "[]"
        if isinstance(value, list):
            return json.dumps(value)
        return value

    def process_result_value(self, value: Any, dialect) -> list[int]:
        if dialect.name == "postgresql":
            return value if isinstance(value, list) else []
        # SQLite: deserialize from JSON
        if value is None:
            return []
        if isinstance(value, list):
            return value
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []


class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=2097152)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    received_chunks: Mapped[list] = mapped_column(IntListType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["Event"] = relationship(  # noqa: F821
        "Event", lazy="select", foreign_keys=[event_id]
    )
    uploader: Mapped["User"] = relationship(  # noqa: F821
        "User", lazy="select", foreign_keys=[uploader_id]
    )
