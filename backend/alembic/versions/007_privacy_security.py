"""Privacy & Security: consent_records and removal_requests tables

Revision ID: 007
Revises: 006
Create Date: 2026-06-23

Per ADR 2026-06-23 (audit-tables-no-fk-survive-purge):
  - event_id and confirmed_by are bare indexed UUID columns with NO FK.
  - This ensures these audit records survive db.delete(event) cascade in
    the 30-day purge job (app/services/purge.py).
  - Do NOT add ForeignKey constraints to these columns in future migrations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # consent_records: owner consent confirmation at event publish.
    # Retained ≥3y, independent of event lifecycle. No FK by design.
    op.create_table(
        "consent_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        # Bare UUID — no FK (ADR 2026-06-23).
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Bare UUID — no FK. Stores the photographer/owner user id.
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "confirmed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_consent_records_event_id",
        "consent_records",
        ["event_id"],
    )

    # removal_requests: guest face-data removal requests.
    # Never deleted (REQ-16). Retained ≥3y. No FK by design.
    op.create_table(
        "removal_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        # Bare UUID — no FK (ADR 2026-06-23).
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("guest_name", sa.Text(), nullable=False),
        sa.Column("guest_email", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("fulfilled_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_removal_requests_event_id",
        "removal_requests",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_removal_requests_event_id", table_name="removal_requests")
    op.drop_table("removal_requests")

    op.drop_index("ix_consent_records_event_id", table_name="consent_records")
    op.drop_table("consent_records")
