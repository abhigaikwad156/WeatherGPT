"""Retrieval and context filtering boundary before an LLM."""

from app.rag.embeddings import EmbeddingProvider
from app.rag.repository import ChunkRepository
from app.rag.types import RetrievalFilter, RetrievedChunk


class RetrievalService:
    def __init__(self, repository: ChunkRepository, embedding_provider: EmbeddingProvider):
        self.repository = repository
        self.embedding_provider = embedding_provider

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: RetrievalFilter | None = None,
        minimum_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        results = self.repository.search(
            tuple(self.embedding_provider.embed(query)), limit, filters
        )
        return [result for result in results if result.score >= minimum_score]

    @staticmethod
    def context(results: list[RetrievedChunk]) -> list[dict[str, object]]:
        return [
            {
                "text": result.chunk.text,
                "score": result.score,
                "source": {
                    "source_id": result.chunk.metadata.source_id,
                    "title": result.chunk.metadata.title,
                    "publisher": result.chunk.metadata.publisher,
                    "source_uri": result.chunk.metadata.source_uri,
                    "publication_date": result.chunk.metadata.publication_date,
                    "document_type": result.chunk.metadata.document_type,
                    "language": result.chunk.metadata.language,
                },
            }
            for result in results
        ]
