"""Album visibility: add public/private field

Revision ID: 008
Revises: 007
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE album_visibility AS ENUM ('public', 'private')")
    op.add_column(
        "albums",
        sa.Column(
            "visibility",
            sa.Enum("public", "private", name="album_visibility"),
            server_default="public",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("albums", "visibility")
    op.execute("DROP TYPE album_visibility")
