"""Admin Platform & Analytics: view_events, download_events, search_events

Revision ID: 009
Revises: 008
Create Date: 2026-08-15

Per design D5 (docs/features/admin-platform/design.md): three event-scoped
analytics tables, one row per action, no guest identity. Unlike the privacy
& security audit tables (consent_records/removal_requests), these ARE
FK-linked with ON DELETE CASCADE — they are lifetime-of-the-event analytics,
not a compliance-retention record, so it's correct for them to disappear
when the event is hard-deleted or purged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("view_events", "download_events", "search_events")


def upgrade() -> None:
    for table_name in _TABLES:
        op.create_table(
            table_name,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "event_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "occurred_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            f"ix_{table_name}_event_id_occurred_at",
            table_name,
            ["event_id", "occurred_at"],
        )


def downgrade() -> None:
    for table_name in _TABLES:
        op.drop_index(f"ix_{table_name}_event_id_occurred_at", table_name=table_name)
        op.drop_table(table_name)
