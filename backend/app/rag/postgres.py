"""PostgreSQL/pgvector chunk repository.

The vector dimension is fixed by the migration and must match the configured
embedding model. This adapter is intentionally separate from the in-memory test store.
"""

import json
from collections.abc import Iterable

from sqlalchemy import Engine, text

from app.rag.repository import ChunkRepository
from app.rag.types import DocumentChunk, RetrievalFilter, RetrievedChunk, SourceMetadata


class PgVectorChunkRepository(ChunkRepository):
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add_many(self, chunks: Iterable[DocumentChunk]) -> None:
        rows = [
            {
                "chunk_id": str(chunk.chunk_id),
                "document_id": str(chunk.document_id),
                "ordinal": chunk.ordinal,
                "content": chunk.text,
                "metadata": json.dumps(chunk.metadata.__dict__),
                "embedding": "[" + ",".join(str(value) for value in (chunk.embedding or ())) + "]",
            }
            for chunk in chunks
        ]
        if not rows:
            return
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO agricultural_document_chunks
                        (chunk_id, document_id, ordinal, content, metadata, embedding)
                    VALUES
                        (:chunk_id, :document_id, :ordinal, :content, CAST(:metadata AS jsonb),
                         CAST(:embedding AS vector))
                    ON CONFLICT (chunk_id) DO NOTHING
                    """
                ),
                rows,
            )

    def search(
        self, embedding: tuple[float, ...], limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        clauses = ["1 = 1"]
        params: dict[str, object] = {
            "embedding": "[" + ",".join(str(value) for value in embedding) + "]",
            "limit": limit,
        }
        for field in ("document_type", "language", "publisher", "source_id"):
            value = getattr(filters, field, None) if filters else None
            if value:
                clauses.append(f"metadata ->> '{field}' = :{field}")
                params[field] = value
        statement = text(
            f"""
            SELECT chunk_id, document_id, ordinal, content, metadata,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM agricultural_document_chunks
            WHERE {" AND ".join(clauses)}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement, params).mappings().all()
        return [
            RetrievedChunk(
                DocumentChunk(
                    document_id=row["document_id"],
                    chunk_id=row["chunk_id"],
                    text=row["content"],
                    ordinal=row["ordinal"],
                    metadata=SourceMetadata(**row["metadata"]),
                ),
                float(row["score"]),
            )
            for row in rows
        ]
