"""Retrieval and context filtering boundary before an LLM."""

import logging

from app.rag.embeddings import EmbeddingProvider
from app.rag.repository import ChunkRepository
from app.rag.types import RetrievalFilter, RetrievedChunk

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        repository: ChunkRepository,
        embedding_provider: EmbeddingProvider | None,
        minimum_score: float = 0.0,
    ):
        if not -1.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between -1 and 1")
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.minimum_score = minimum_score

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: RetrievalFilter | None = None,
        minimum_score: float | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self.embedding_provider is None:
            logger.warning("Agricultural embeddings are unavailable; using lexical retrieval")
            return self.repository.search_text(query, limit, filters)
        try:
            embedding = tuple(self.embedding_provider.embed(query))
        except RuntimeError as error:
            logger.warning(
                "Agricultural query embedding failed; using lexical retrieval (%s)",
                type(error).__name__,
            )
            return self.repository.search_text(query, limit, filters)
        results = self.repository.search(embedding, limit, filters)
        score_floor = self.minimum_score if minimum_score is None else minimum_score
        if not -1.0 <= score_floor <= 1.0:
            raise ValueError("minimum_score must be between -1 and 1")
        return [result for result in results if result.score >= score_floor]

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
