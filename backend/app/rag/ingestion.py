"""Trusted agricultural document ingestion pipeline."""

from collections.abc import Iterable

from app.rag.chunking import chunk_document
from app.rag.embeddings import EmbeddingProvider
from app.rag.extract import extract_text
from app.rag.repository import ChunkRepository
from app.rag.types import AgriculturalDocument, DocumentChunk, SourceMetadata


class DocumentIngestionService:
    def __init__(
        self,
        repository: ChunkRepository,
        embedding_provider: EmbeddingProvider,
        trusted_publishers: Iterable[str],
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.trusted_publishers = frozenset(trusted_publishers)

    def ingest(
        self,
        content: bytes,
        mime_type: str,
        metadata: SourceMetadata,
        *,
        max_characters: int = 1200,
        overlap: int = 120,
    ) -> list[DocumentChunk]:
        if not metadata.trusted or metadata.publisher not in self.trusted_publishers:
            raise ValueError(
                "document publisher is not in the trusted agricultural source allowlist"
            )
        document = AgriculturalDocument(extract_text(content, mime_type), metadata)
        chunks = [
            DocumentChunk(
                chunk.document_id,
                chunk.chunk_id,
                chunk.text,
                chunk.metadata,
                chunk.ordinal,
                tuple(self.embedding_provider.embed(chunk.text)),
            )
            for chunk in chunk_document(document, max_characters=max_characters, overlap=overlap)
        ]
        self.repository.add_many(chunks)
        return chunks
