"""Add gallery columns and indexes to photos table

Revision ID: 004
Revises: 003
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column(
            "download_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "photos",
        sa.Column(
            "is_photographer_choice",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "photos",
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
    )

    # Gallery composite indexes
    op.create_index(
        "ix_photos_gallery_all_latest",
        "photos",
        ["event_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_photos_gallery_all_popular",
        "photos",
        ["event_id", sa.text("download_count DESC")],
    )
    op.create_index(
        "ix_photos_gallery_all_choice",
        "photos",
        ["event_id", sa.text("is_photographer_choice DESC"), sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_photos_gallery_alb_latest",
        "photos",
        ["event_id", "album_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_photos_gallery_alb_popular",
        "photos",
        ["event_id", "album_id", sa.text("download_count DESC")],
    )
    op.create_index(
        "ix_photos_gallery_alb_choice",
        "photos",
        ["event_id", "album_id", sa.text("is_photographer_choice DESC"), sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_photos_gallery_alb_choice", table_name="photos")
    op.drop_index("ix_photos_gallery_alb_popular", table_name="photos")
    op.drop_index("ix_photos_gallery_alb_latest", table_name="photos")
    op.drop_index("ix_photos_gallery_all_choice", table_name="photos")
    op.drop_index("ix_photos_gallery_all_popular", table_name="photos")
    op.drop_index("ix_photos_gallery_all_latest", table_name="photos")
    op.drop_column("photos", "thumbnail_path")
    op.drop_column("photos", "is_photographer_choice")
    op.drop_column("photos", "download_count")
