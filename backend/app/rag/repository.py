"""Storage contracts and an in-memory implementation for tests."""

from collections.abc import Iterable

from app.rag.embeddings import cosine_similarity
from app.rag.types import DocumentChunk, RetrievalFilter, RetrievedChunk


class ChunkRepository:
    def add_many(self, chunks: Iterable[DocumentChunk]) -> None:
        raise NotImplementedError

    def search(
        self, embedding: tuple[float, ...], limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        raise NotImplementedError


class InMemoryChunkRepository(ChunkRepository):
    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []

    def add_many(self, chunks: Iterable[DocumentChunk]) -> None:
        self.chunks.extend(chunks)

    def search(
        self, embedding: tuple[float, ...], limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        matches = []
        for chunk in self.chunks:
            metadata = chunk.metadata
            if filters and (
                (filters.document_type and metadata.document_type != filters.document_type)
                or (filters.language and metadata.language != filters.language)
                or (filters.publisher and metadata.publisher != filters.publisher)
                or (filters.source_id and metadata.source_id != filters.source_id)
            ):
                continue
            if chunk.embedding is not None:
                matches.append(RetrievedChunk(chunk, cosine_similarity(embedding, chunk.embedding)))
        return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]
