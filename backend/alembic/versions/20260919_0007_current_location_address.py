"""Store normalized reverse-geocoded current location metadata.

Revision ID: 20260919_0007
Revises: 20260918_0006
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0007"
down_revision: str | None = "20260918_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_current_locations", sa.Column("location_name", sa.String(160)))
    op.add_column("user_current_locations", sa.Column("city", sa.String(120)))
    op.add_column("user_current_locations", sa.Column("district", sa.String(120)))
    op.add_column("user_current_locations", sa.Column("state", sa.String(120)))
    op.add_column("user_current_locations", sa.Column("country", sa.String(120)))
    op.add_column("user_current_locations", sa.Column("country_code", sa.String(2)))


def downgrade() -> None:
    op.drop_column("user_current_locations", "country_code")
    op.drop_column("user_current_locations", "country")
    op.drop_column("user_current_locations", "state")
    op.drop_column("user_current_locations", "district")
    op.drop_column("user_current_locations", "city")
    op.drop_column("user_current_locations", "location_name")
