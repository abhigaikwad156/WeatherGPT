"""PostgreSQL/pgvector chunk repository.

The vector dimension is fixed by the migration and must match the configured
embedding model. This adapter is intentionally separate from the in-memory test store.
"""

import json
from collections.abc import Iterable

from sqlalchemy import Engine, text

from app.rag.repository import ChunkRepository, lexical_query_tokens
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
            for document_id in {row["document_id"] for row in rows}:
                connection.execute(
                    text(
                        "DELETE FROM agricultural_document_chunks "
                        "WHERE document_id = CAST(:document_id AS uuid)"
                    ),
                    {"document_id": document_id},
                )
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

    def search_text(
        self, query: str, limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        tokens = lexical_query_tokens(query)[:32]
        if not tokens:
            return []
        config = "simple" if any(ord(character) > 127 for character in query) else "english"
        vector = f"to_tsvector('{config}', content)"
        query_expression = f"to_tsquery('{config}', :query)"
        term_match = " + ".join(
            f"CASE WHEN {vector} @@ to_tsquery('{config}', :term_{index}) "
            f"THEN 1 ELSE 0 END"
            for index in range(len(tokens))
        )
        minimum_matches = min(2, len(tokens))
        clauses = [f"{vector} @@ {query_expression}", f"({term_match}) >= :minimum_matches"]
        params: dict[str, object] = {
            "query": " | ".join(f"{token}:*" for token in tokens),
            "limit": limit,
            "minimum_matches": minimum_matches,
        }
        params.update({f"term_{index}": f"{token}:*" for index, token in enumerate(tokens)})
        for field in ("document_type", "language", "publisher", "source_id"):
            value = getattr(filters, field, None) if filters else None
            if value:
                clauses.append(f"metadata ->> '{field}' = :{field}")
                params[field] = value
        statement = text(
            f"""
            SELECT chunk_id, document_id, ordinal, content, metadata,
                   ts_rank_cd({vector}, {query_expression}) AS score
            FROM agricultural_document_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY score DESC, ordinal
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
