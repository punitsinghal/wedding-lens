"""Add photo_id and r2_upload_id columns to upload_sessions

Revision ID: 011
Revises: 010
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "upload_sessions",
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "upload_sessions",
        sa.Column("r2_upload_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("upload_sessions", "r2_upload_id")
    op.drop_column("upload_sessions", "photo_id")
