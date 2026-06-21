"""Photographer dashboard: upload sessions, photo_albums, event_photographers, and photo columns

Revision ID: 006
Revises: 005
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # upload_sessions table
    op.create_table(
        "upload_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "chunk_size_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2097152"),
        ),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column(
            "received_chunks",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'in_progress'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_upload_sessions_event_hash",
        "upload_sessions",
        ["event_id", "content_hash"],
    )
    op.create_index(
        "ix_upload_sessions_status_updated",
        "upload_sessions",
        ["status", "updated_at"],
    )

    # photo_albums join table
    op.create_table(
        "photo_albums",
        sa.Column(
            "photo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "album_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )

    # event_photographers table
    op.create_table(
        "event_photographers",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "photographer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "assigned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Alter photos table
    op.add_column("photos", sa.Column("content_hash", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("face_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_photos_event_content_hash",
        "photos",
        ["event_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_photos_event_content_hash", table_name="photos")
    op.drop_column("photos", "face_error")
    op.drop_column("photos", "content_hash")

    op.drop_table("event_photographers")
    op.drop_table("photo_albums")

    op.drop_index("ix_upload_sessions_status_updated", table_name="upload_sessions")
    op.drop_index("ix_upload_sessions_event_hash", table_name="upload_sessions")
    op.drop_table("upload_sessions")
