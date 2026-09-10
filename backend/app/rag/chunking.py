"""Deterministic, source-preserving text chunking."""

from uuid import uuid4

from app.rag.types import AgriculturalDocument, DocumentChunk


def chunk_document(
    document: AgriculturalDocument, *, max_characters: int = 1200, overlap: int = 120
) -> list[DocumentChunk]:
    if max_characters <= 0 or overlap < 0 or overlap >= max_characters:
        raise ValueError("overlap must be non-negative and smaller than max_characters")
    words = document.text.split()
    chunks: list[DocumentChunk] = []
    current: list[str] = []
    length = 0
    ordinal = 0
    for word in words:
        if current and length + len(word) + 1 > max_characters:
            text = " ".join(current)
            chunks.append(
                DocumentChunk(document.document_id, uuid4(), text, document.metadata, ordinal)
            )
            ordinal += 1
            tail: list[str] = []
            tail_length = 0
            for previous in reversed(current):
                if tail_length + len(previous) + 1 > overlap:
                    break
                tail.insert(0, previous)
                tail_length += len(previous) + 1
            current = tail
            length = tail_length
        current.append(word)
        length += len(word) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(
            DocumentChunk(
                document.document_id,
                uuid4(),
                " ".join(current),
                document.metadata,
                ordinal,
            )
        )
    return chunks
