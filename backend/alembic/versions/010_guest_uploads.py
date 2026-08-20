"""Add guest uploads columns to events and photos

Revision ID: 010
Revises: 009
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "guest_uploads_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "photos",
        sa.Column(
            "uploaded_by",
            sa.String(20),
            nullable=False,
            server_default="photographer",
        ),
    )
    op.add_column(
        "photos",
        sa.Column("guest_display_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "guest_display_name")
    op.drop_column("photos", "uploaded_by")
    op.drop_column("events", "guest_uploads_enabled")
