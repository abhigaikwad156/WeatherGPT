import pytest

from app.rag.chunking import chunk_document
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.ingestion import DocumentIngestionService
from app.rag.repository import InMemoryChunkRepository
from app.rag.retrieval import RetrievalService
from app.rag.types import AgriculturalDocument, RetrievalFilter, SourceMetadata


def metadata(**changes: object) -> SourceMetadata:
    values = {
        "source_id": "gov-001",
        "title": "Irrigation guide",
        "publisher": "Agriculture Department",
        "document_type": "irrigation",
        "trusted": True,
    }
    return SourceMetadata(**{**values, **changes})


def test_chunking_retains_document_source_metadata() -> None:
    document = AgriculturalDocument("one two three four five six", metadata())
    chunks = chunk_document(document, max_characters=12, overlap=0)
    assert len(chunks) > 1
    assert all(chunk.metadata.source_id == "gov-001" for chunk in chunks)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_ingestion_rejects_untrusted_publishers() -> None:
    service = DocumentIngestionService(
        InMemoryChunkRepository(), HashEmbeddingProvider(), {"Agriculture Department"}
    )
    with pytest.raises(ValueError, match="trusted"):
        service.ingest(b"agricultural content", "text/plain", metadata(trusted=False))


def test_retrieval_filters_metadata_and_returns_source_context() -> None:
    repository = InMemoryChunkRepository()
    service = DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    )
    service.ingest(
        b"Use irrigation guidance for soil moisture and water scheduling.",
        "text/plain",
        metadata(language="en"),
    )
    service.ingest(
        b"Weather disaster preparedness guidance for heavy rainfall.",
        "text/plain",
        metadata(
            source_id="gov-002",
            title="Disaster guide",
            document_type="disaster",
        ),
    )
    retrieval = RetrievalService(repository, HashEmbeddingProvider())
    results = retrieval.retrieve(
        "soil moisture irrigation", filters=RetrievalFilter(document_type="irrigation")
    )
    context = retrieval.context(results)
    assert results
    assert context[0]["source"]["source_id"] == "gov-001"
    assert context[0]["source"]["publisher"] == "Agriculture Department"
