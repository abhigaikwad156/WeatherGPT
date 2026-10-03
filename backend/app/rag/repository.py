"""Storage contracts and an in-memory implementation for tests."""

import re
from collections.abc import Iterable

from app.rag.embeddings import cosine_similarity
from app.rag.types import DocumentChunk, RetrievalFilter, RetrievedChunk

_LEXICAL_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "should", "the", "to", "was", "what", "when", "where", "which",
    "who", "why", "with", "would",
}


def lexical_query_tokens(query: str) -> list[str]:
    tokens = []
    for token in re.findall(r"\w+", query.casefold()):
        if token in _LEXICAL_STOP_WORDS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if token not in tokens:
            tokens.append(token)
    return tokens


class ChunkRepository:
    def add_many(self, chunks: Iterable[DocumentChunk]) -> None:
        raise NotImplementedError

    def search(
        self, embedding: tuple[float, ...], limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        raise NotImplementedError

    def search_text(
        self, query: str, limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        raise NotImplementedError


class InMemoryChunkRepository(ChunkRepository):
    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []

    def add_many(self, chunks: Iterable[DocumentChunk]) -> None:
        new_chunks = list(chunks)
        document_ids = {chunk.document_id for chunk in new_chunks}
        self.chunks = [chunk for chunk in self.chunks if chunk.document_id not in document_ids]
        self.chunks.extend(new_chunks)

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

    def search_text(
        self, query: str, limit: int, filters: RetrievalFilter | None = None
    ) -> list[RetrievedChunk]:
        query_tokens = set(lexical_query_tokens(query))
        if not query_tokens:
            return []
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
            content_tokens = set(lexical_query_tokens(chunk.text))
            overlap = query_tokens & content_tokens
            if len(overlap) >= min(2, len(query_tokens)):
                score = len(overlap) / len(query_tokens)
                matches.append(RetrievedChunk(chunk, score))
        return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]
