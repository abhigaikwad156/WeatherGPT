"""Store timestamped sensor and crop irrigation inputs.

Revision ID: 20261112_0009
Revises: 20261020_0008
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261112_0009"
down_revision: str | None = "20261020_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("farms", sa.Column("region", sa.String(120), nullable=True))
    op.add_column("farms", sa.Column("irrigation_layout", sa.String(80), nullable=True))
    op.add_column(
        "farms",
        sa.Column(
            "irrigation_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "farms",
        sa.Column("soil_moisture_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("farmer_crops", sa.Column("last_irrigated_at", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("farmer_crops", "last_irrigated_at")
    op.drop_column("farms", "soil_moisture_measured_at")
    op.drop_column("farms", "irrigation_configuration")
    op.drop_column("farms", "irrigation_layout")
    op.drop_column("farms", "region")
