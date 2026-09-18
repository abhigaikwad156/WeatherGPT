"""Add current device locations and optional farm location metadata.

Revision ID: 20260918_0006
Revises: 20260910_0005
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260918_0006"
down_revision: str | None = "20260910_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_current_locations",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("latitude", sa.Numeric(8, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("accuracy_meters", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name="ck_user_current_locations_latitude_range"
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_user_current_locations_longitude_range"
        ),
        sa.CheckConstraint(
            "accuracy_meters IS NULL OR accuracy_meters > 0",
            name="ck_user_current_locations_accuracy_positive",
        ),
    )
    op.add_column("farms", sa.Column("location_name", sa.String(length=160), nullable=True))
    op.add_column("farms", sa.Column("location_accuracy_meters", sa.Numeric(10, 2), nullable=True))
    op.create_check_constraint(
        "ck_farms_location_accuracy_positive",
        "farms",
        "location_accuracy_meters IS NULL OR location_accuracy_meters > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_farms_location_accuracy_positive", "farms", type_="check")
    op.drop_column("farms", "location_accuracy_meters")
    op.drop_column("farms", "location_name")
    op.drop_table("user_current_locations")
