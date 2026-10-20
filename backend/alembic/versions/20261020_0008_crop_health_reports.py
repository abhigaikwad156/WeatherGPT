"""Create persistent crop health reports.

Revision ID: 20261020_0008
Revises: 20260919_0007
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261020_0008"
down_revision: str | None = "20260919_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crop_health_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "farm_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("farms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "crop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("farmer_crops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symptoms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_days BETWEEN 1 AND 365",
            name="ck_crop_health_reports_duration_range",
        ),
    )
    op.create_index(
        "ix_crop_health_reports_owner_created",
        "crop_health_reports",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_crop_health_reports_owner_created", table_name="crop_health_reports")
    op.drop_table("crop_health_reports")
