"""Add normalized weather condition fields.

Revision ID: 20260910_0004
Revises: 20260910_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0004"
down_revision: str | None = "20260910_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("weather_observations", sa.Column("condition", sa.String(length=120)))
    op.add_column("weather_forecasts", sa.Column("condition", sa.String(length=120)))


def downgrade() -> None:
    op.drop_column("weather_forecasts", "condition")
    op.drop_column("weather_observations", "condition")
