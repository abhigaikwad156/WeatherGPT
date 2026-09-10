"""Contracts for agricultural knowledge ingestion and retrieval."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    title: str
    publisher: str
    source_uri: str | None = None
    publication_date: str | None = None
    language: str = "en"
    document_type: str = "guidance"
    trusted: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgriculturalDocument:
    text: str
    metadata: SourceMetadata
    document_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class DocumentChunk:
    document_id: UUID
    chunk_id: UUID
    text: str
    metadata: SourceMetadata
    ordinal: int
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float


@dataclass(frozen=True)
class RetrievalFilter:
    document_type: str | None = None
    language: str | None = None
    publisher: str | None = None
    source_id: str | None = None
