"""Add trusted agricultural RAG chunks backed by pgvector.

Revision ID: 20260910_0005
Revises: 20260910_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260910_0005"
down_revision: str | None = "20260910_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "agricultural_document_chunks",
        sa.Column("chunk_id", sa.UUID(), primary_key=True),
        sa.Column("document_id", sa.UUID(), nullable=False, index=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
    )
    op.execute(
        "ALTER TABLE agricultural_document_chunks "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    op.execute(
        "CREATE INDEX ix_agricultural_chunks_embedding ON agricultural_document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("agricultural_document_chunks")
