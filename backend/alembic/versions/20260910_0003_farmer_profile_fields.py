"""Add farmer profile and farm detail fields.

Revision ID: 20260910_0003
Revises: 20260910_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0003"
down_revision: str | None = "20260910_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("location", sa.String(length=160), nullable=True))
    op.add_column(
        "users",
        sa.Column("preferred_units", sa.String(length=20), server_default="metric", nullable=False),
    )
    op.add_column("farms", sa.Column("soil_type", sa.String(length=80), nullable=True))
    op.add_column("farms", sa.Column("irrigation_type", sa.String(length=80), nullable=True))
    op.add_column(
        "farms", sa.Column("soil_moisture_percent", sa.Numeric(5, 2), nullable=True)
    )
    op.create_check_constraint(
        "ck_farms_soil_moisture_range",
        "farms",
        "soil_moisture_percent IS NULL OR soil_moisture_percent BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_farms_soil_moisture_range", "farms", type_="check")
    op.drop_column("farms", "soil_moisture_percent")
    op.drop_column("farms", "irrigation_type")
    op.drop_column("farms", "soil_type")
    op.drop_column("users", "preferred_units")
    op.drop_column("users", "location")
