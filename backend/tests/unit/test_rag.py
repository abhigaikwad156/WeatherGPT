from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.rag.chunking import chunk_document
from app.rag.embeddings import GeminiEmbeddingProvider, HashEmbeddingProvider
from app.rag.extract import extract_text
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


def make_text_pdf(text: str | None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    if text is not None:
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 240 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_chunking_retains_document_source_metadata() -> None:
    document = AgriculturalDocument("one two three four five six", metadata())
    chunks = chunk_document(document, max_characters=12, overlap=0)
    assert len(chunks) > 1
    assert all(chunk.metadata.source_id == "gov-001" for chunk in chunks)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_gemini_embedding_provider_requests_configured_retrieval_dimension() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert request.url.path.endswith("/models/gemini-embedding-001:embedContent")
        payload = request.read().decode()
        assert '"outputDimensionality":1536' in payload
        assert '"taskType":"RETRIEVAL_QUERY"' in payload
        return httpx.Response(200, json={"embedding": {"values": [0.25] * 1536}})

    provider = GeminiEmbeddingProvider(
        "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    embedding = provider.embed("irrigation guidance")

    assert len(embedding) == 1536
    assert embedding[0] == 0.25


def test_gemini_embedding_provider_rejects_wrong_dimension() -> None:
    import httpx

    provider = GeminiEmbeddingProvider(
        "test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"embedding": {"values": [0.1]}})
            )
        ),
    )

    with pytest.raises(RuntimeError, match="1536"):
        provider.embed("irrigation guidance")


def test_gemini_batch_embedding_preserves_order_and_chunks_requests() -> None:
    import httpx

    batch_lengths: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert request.url.path.endswith("/models/gemini-embedding-001:batchEmbedContents")
        batch = payload["requests"]
        batch_lengths.append(len(batch))
        values = [float(index + 1) for index in range(1536)]
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": [value * len(batch) for value in values]} for _ in batch
                ]
            },
        )

    provider = GeminiEmbeddingProvider(
        "batch-test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    texts = [f"chunk {index}" for index in range(17)]

    embeddings = provider.embed_many(texts)

    assert batch_lengths == [16, 1]
    assert len(embeddings) == len(texts)
    assert embeddings[0][0] == 16.0
    assert embeddings[-1][0] == 1.0


def test_ingestion_prefers_batch_embedding_provider() -> None:
    class BatchProvider:
        dimension = 3

        def embed(self, text: str, *, task_type: str = "RETRIEVAL_QUERY") -> tuple[float, ...]:
            raise AssertionError("single embedding should not be used")

        def embed_many(
            self, texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT"
        ) -> list[tuple[float, ...]]:
            assert task_type == "RETRIEVAL_DOCUMENT"
            return [(float(index), 0.0, 1.0) for index, _ in enumerate(texts)]

    repository = InMemoryChunkRepository()
    service = DocumentIngestionService(repository, BatchProvider(), {"Agriculture Department"})

    chunks = service.ingest(
        b"first document chunk. second document chunk.",
        "text/plain",
        metadata(),
        max_characters=12,
        overlap=0,
    )

    assert len(chunks) > 1
    assert [chunk.embedding[0] for chunk in chunks] == [
        float(index) for index in range(len(chunks))
    ]


def test_gemini_embedding_provider_honors_quota_retry_delay() -> None:
    import httpx

    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            json={
                "error": {
                    "details": [
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3600s"}
                    ]
                }
            },
        )

    provider = GeminiEmbeddingProvider(
        "cooldown-test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(RuntimeError, match="3600 seconds"):
        provider.embed("quota cooldown test")
    with pytest.raises(RuntimeError, match="cooldown is active"):
        provider.embed("quota cooldown test")
    assert calls == 1


def test_ingestion_rejects_untrusted_publishers() -> None:
    service = DocumentIngestionService(
        InMemoryChunkRepository(), HashEmbeddingProvider(), {"Agriculture Department"}
    )
    with pytest.raises(ValueError, match="trusted"):
        service.ingest(b"agricultural content", "text/plain", metadata(trusted=False))


def test_pdf_ingestion_extracts_text_and_runs_through_chunking_and_embeddings() -> None:
    repository = InMemoryChunkRepository()
    service = DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    )

    chunks = service.ingest(
        make_text_pdf("Irrigation guidance for wheat crops."),
        "application/pdf",
        metadata(),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "Irrigation guidance for wheat crops."
    assert len(chunks[0].embedding or ()) == 64
    assert repository.chunks == chunks


def test_pdf_extraction_rejects_empty_scanned_and_unsupported_documents() -> None:
    with pytest.raises(ValueError, match="empty or scanned"):
        extract_text(make_text_pdf(None), "application/pdf")
    with pytest.raises(ValueError, match="plain text, HTML, and PDF"):
        extract_text(b"unsupported", "application/octet-stream")


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


def test_retrieval_reingest_replaces_existing_document_chunks() -> None:
    repository = InMemoryChunkRepository()
    ingestion = DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    )
    source = metadata()
    first = ingestion.ingest(b"First irrigation guide content.", "text/plain", source)
    replacement = ingestion.ingest(b"Updated irrigation guide content.", "text/plain", source)

    assert len(repository.chunks) == len(replacement) == 1
    assert repository.chunks[0].chunk_id == first[0].chunk_id
    assert repository.chunks[0].text == "Updated irrigation guide content."


def test_lexical_fallback_requires_topic_and_crop_overlap() -> None:
    repository = InMemoryChunkRepository()
    DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    ).ingest(
        b"Sugarcane grows widely across tropical regions.",
        "text/plain",
        metadata(source_id="crop-only"),
    )
    DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    ).ingest(
        b"Sugarcane disease symptoms include leaf lesions caused by fungal infection.",
        "text/plain",
        metadata(source_id="disease-guide"),
    )

    results = repository.search_text("What diseases affect sugarcane?", 5)

    assert [item.chunk.metadata.source_id for item in results] == ["disease-guide"]


def test_retrieval_falls_back_to_lexical_search_when_embedding_fails() -> None:
    repository = InMemoryChunkRepository()
    DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    ).ingest(
        b"Sugarcane irrigation guidance describes drip scheduling.",
        "text/plain",
        metadata(source_id="sugarcane-irrigation"),
    )

    class UnavailableEmbeddingProvider:
        dimension = 1536

        def embed(self, text: str, *, task_type: str = "RETRIEVAL_QUERY") -> tuple[float, ...]:
            raise RuntimeError("embedding quota exhausted")

    retrieval = RetrievalService(repository, UnavailableEmbeddingProvider())

    results = retrieval.retrieve("sugarcane irrigation practices")

    assert len(results) == 1
    assert results[0].chunk.metadata.source_id == "sugarcane-irrigation"
