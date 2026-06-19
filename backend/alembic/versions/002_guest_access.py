"""Add guest access columns to events

Revision ID: 002
Revises: 001
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("otp_code", sa.String(255), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "guest_access_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "events",
        sa.Column("guest_access_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "guest_access_revoked_at")
    op.drop_column("events", "guest_access_enabled")
    op.drop_column("events", "otp_code")
