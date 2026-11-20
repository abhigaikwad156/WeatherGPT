"""Trusted agricultural document ingestion pipeline."""

from collections.abc import Callable, Iterable
from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

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
        on_progress: Callable[[str, int], None] | None = None,
    ) -> list[DocumentChunk]:
        if not metadata.trusted or metadata.publisher not in self.trusted_publishers:
            raise ValueError(
                "document publisher is not in the trusted agricultural source allowlist"
            )
        provider_name = getattr(self.embedding_provider, "provider_name", None)
        model_name = getattr(self.embedding_provider, "model_name", None)
        if provider_name and model_name:
            metadata = replace(
                metadata,
                embedding_provider=provider_name,
                embedding_model=model_name,
            )
        document_id = uuid5(NAMESPACE_URL, f"weathergpt:{metadata.source_id}")
        document = AgriculturalDocument(extract_text(content, mime_type), metadata, document_id)
        document_chunks = chunk_document(
            document, max_characters=max_characters, overlap=overlap
        )
        if on_progress:
            on_progress("chunks", len(document_chunks))
        embed_many = getattr(self.embedding_provider, "embed_many", None)
        if callable(embed_many):
            embeddings = embed_many(
                [chunk.text for chunk in document_chunks], task_type="RETRIEVAL_DOCUMENT"
            )
        else:
            embeddings = [
                self.embedding_provider.embed(chunk.text, task_type="RETRIEVAL_DOCUMENT")
                for chunk in document_chunks
            ]
        if on_progress:
            on_progress("embeddings", len(embeddings))
        chunks = [
            DocumentChunk(
                chunk.document_id,
                chunk.chunk_id,
                chunk.text,
                chunk.metadata,
                chunk.ordinal,
                tuple(embedding),
            )
            for chunk, embedding in zip(document_chunks, embeddings, strict=True)
        ]
        self.repository.add_many(chunks)
        if on_progress:
            on_progress("stored", len(chunks))
        return chunks
