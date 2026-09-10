"""Create the initial migration baseline.

Revision ID: 20260910_0001
Revises:
Create Date: 2026-09-10
"""

from collections.abc import Sequence

revision: str = "20260910_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Reserve a reproducible baseline before domain tables are introduced."""


def downgrade() -> None:
    """The initial baseline has no schema objects to remove."""
