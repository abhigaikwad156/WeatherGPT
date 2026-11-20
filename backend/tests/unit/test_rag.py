import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.rag.chunking import chunk_document
from app.rag.embeddings import (
    AlibabaEmbeddingProvider,
    CohereEmbeddingProvider,
    GeminiEmbeddingProvider,
    HashEmbeddingProvider,
)
from app.rag.extract import extract_text
from app.rag.ingest_cli import ingest_source
from app.rag.ingestion import DocumentIngestionService
from app.rag.postgres import PgVectorChunkRepository
from app.rag.repository import InMemoryChunkRepository
from app.rag.retrieval import RetrievalService
from app.rag.types import AgriculturalDocument, RetrievalFilter, SourceMetadata
from app.rag.web import fetch_web_document


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


def test_alibaba_embedding_provider_uses_official_compatible_api_and_dimensions() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-dashscope-key"
        payload = json.loads(request.content)
        assert payload["model"] == "text-embedding-v4"
        assert payload["input"] == ["document text", "query text"]
        assert payload["dimensions"] == 1536
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2] * 1536},
                    {"index": 0, "embedding": [0.1] * 1536},
                ]
            },
        )

    provider = AlibabaEmbeddingProvider(
        "test-dashscope-key",
        "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    embeddings = provider.embed_many(["document text", "query text"])

    assert provider.provider_name == "alibaba"
    assert provider.model_name == "text-embedding-v4"
    assert len(embeddings) == 2
    assert len(embeddings[0]) == len(embeddings[1]) == 1536
    assert embeddings[0][0] == 0.1
    assert embeddings[1][0] == 0.2


def test_alibaba_embedding_provider_rejects_wrong_dimension_and_missing_key() -> None:
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        AlibabaEmbeddingProvider(
            "",
            "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        )
    with pytest.raises(ValueError, match="1536"):
        AlibabaEmbeddingProvider(
            "test-key",
            "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
            dimension=768,
        )


def test_alibaba_embedding_provider_rejects_invalid_embedding_response() -> None:
    import httpx

    provider = AlibabaEmbeddingProvider(
        "test-key",
        "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={"data": [{"index": 0, "embedding": [0.1]}]},
                )
            )
        ),
    )

    with pytest.raises(RuntimeError, match="1536"):
        provider.embed("agricultural guidance")


def test_alibaba_embedding_provider_rejects_duplicate_response_indices() -> None:
    import httpx

    provider = AlibabaEmbeddingProvider(
        "test-key",
        "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 0, "embedding": [0.1] * 1536},
                            {"index": 0, "embedding": [0.2] * 1536},
                        ]
                    },
                )
            )
        ),
    )

    with pytest.raises(RuntimeError, match="invalid embedding response"):
        provider.embed_many(["first", "second"])


def test_cohere_embedding_provider_uses_search_input_types_and_1536_dimensions() -> None:
    import httpx

    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.cohere.com/v2/embed"
        assert request.headers["authorization"] == "Bearer test-cohere-key"
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={"embeddings": {"float": [[0.25] * 1536 for _ in payload["texts"]]}},
        )

    provider = CohereEmbeddingProvider(
        "test-cohere-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    query_embedding = provider.embed("sugarcane irrigation")
    document_embeddings = provider.embed_many(
        ["document one", "document two"], task_type="RETRIEVAL_DOCUMENT"
    )

    assert provider.provider_name == "cohere"
    assert provider.model_name == "embed-v4.0"
    assert provider.dimension == 1536
    assert len(query_embedding) == 1536
    assert len(document_embeddings) == 2
    assert requests[0]["input_type"] == "search_query"
    assert requests[1]["input_type"] == "search_document"
    for payload in requests:
        assert payload["model"] == "embed-v4.0"
        assert payload["embedding_types"] == ["float"]
        assert payload["output_dimension"] == 1536


def test_cohere_embedding_provider_rejects_missing_key_and_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="COHERE_API_KEY"):
        CohereEmbeddingProvider("")
    with pytest.raises(ValueError, match="1536"):
        CohereEmbeddingProvider("test-key", dimension=768)


def test_cohere_embedding_provider_reports_quota_errors() -> None:
    import httpx

    provider = CohereEmbeddingProvider(
        "test-cohere-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(429, json={"message": "rate limited"})
            )
        ),
    )

    with pytest.raises(RuntimeError, match="quota exceeded"):
        provider.embed("test query")


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


def test_web_ingestion_uses_existing_pipeline_and_reports_persisted_chunks() -> None:
    import httpx

    url = "https://docs.example/sugarcane.pdf"
    repository = InMemoryChunkRepository()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=make_text_pdf("Sugarcane package of practices and crop management."),
            )
        )
    )

    report = ingest_source(
        url,
        metadata(
            source_id="trusted-sugarcane",
            publisher="Agriculture Department",
            source_uri=url,
            publication_date="2025",
        ),
        repository,
        ["Agriculture Department"],
        ["docs.example"],
        1024 * 1024,
        "",
        "unused-in-test",
        64,
        http_client=client,
        resolver=lambda _host, _port: ["8.8.8.8"],
        embedding_provider=HashEmbeddingProvider(),
    )

    assert report["status"] == "ingested"
    assert report["extracted_text_length"] == len(
        "Sugarcane package of practices and crop management."
    )
    assert report["chunk_count"] == report["embeddings_stored"] == len(repository.chunks) == 1
    assert report["storage"] == "stored"
    assert repository.chunks[0].metadata.source_uri == url
    assert repository.chunks[0].metadata.publication_date == "2025"


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.example/document.pdf",
        "https://untrusted.example/document.pdf",
        "https://docs.example:8443/document.pdf",
        "https://user:password@docs.example/document.pdf",
    ],
)
def test_web_ingestion_rejects_invalid_urls_before_request(url: str) -> None:
    import httpx

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("invalid URL must not trigger a request")
        )
    )

    with pytest.raises(ValueError):
        fetch_web_document(
            url,
            ["docs.example"],
            1024,
            client=client,
            resolver=lambda _host, _port: ["8.8.8.8"],
        )


def test_web_ingestion_rejects_private_dns_results() -> None:
    import httpx

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("private address must not trigger a request")
        )
    )

    with pytest.raises(ValueError, match="non-public IP"):
        fetch_web_document(
            "https://docs.example/document.pdf",
            ["docs.example"],
            1024,
            client=client,
            resolver=lambda _host, _port: ["127.0.0.1"],
        )


@pytest.mark.parametrize(
    ("content_type", "content", "message"),
    [
        ("application/zip", b"archive", "Unsupported document content type"),
        ("application/pdf", b"<html>not a PDF</html>", "does not match"),
        ("text/html", b"\xff\xfe", "UTF-8"),
    ],
)
def test_web_ingestion_rejects_unsupported_document_formats(
    content_type: str, content: bytes, message: str
) -> None:
    import httpx

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, headers={"content-type": content_type}, content=content
            )
        )
    )

    with pytest.raises(ValueError, match=message):
        fetch_web_document(
            "https://docs.example/document",
            ["docs.example"],
            1024,
            client=client,
            resolver=lambda _host, _port: ["8.8.8.8"],
        )


def test_web_ingestion_normalizes_declared_legacy_html_charset() -> None:
    import httpx

    content = b'<html><head><meta charset="iso-8859-1"></head><body>caf\xe9</body></html>'
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, headers={"content-type": "text/html"}, content=content
            )
        )
    )

    document = fetch_web_document(
        "https://docs.example/document",
        ["docs.example"],
        1024,
        client=client,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )

    assert extract_text(document.content, document.mime_type) == "café"


def test_web_ingestion_rejects_unsafe_redirects() -> None:
    import httpx

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            302, headers={"location": "https://attacker.example/document.pdf"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="trusted-domain"):
        fetch_web_document(
            "https://docs.example/document.pdf",
            ["docs.example"],
            1024,
            client=client,
            resolver=lambda _host, _port: ["8.8.8.8"],
        )
    assert requests == ["https://docs.example/document.pdf"]


def test_web_ingestion_skips_duplicate_source_without_replacing_chunks() -> None:
    import httpx

    url = "https://docs.example/sugarcane.pdf"
    repository = InMemoryChunkRepository()
    first_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=make_text_pdf("Sugarcane crop management and varieties."),
            )
        )
    )
    source = metadata(
        source_id="duplicate-sugarcane",
        publisher="Agriculture Department",
        source_uri=url,
    )
    options = {
        "trusted_publishers": ["Agriculture Department"],
        "trusted_domains": ["docs.example"],
        "max_download_bytes": 1024 * 1024,
        "embedding_api_key": "",
        "embedding_model": "unused-in-test",
        "embedding_dimension": 64,
        "resolver": lambda _host, _port: ["8.8.8.8"],
        "embedding_provider": HashEmbeddingProvider(),
    }

    first = ingest_source(url, source, repository, http_client=first_client, **options)
    original_chunks = list(repository.chunks)
    second_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("duplicate URL must not be downloaded")
        )
    )

    duplicate = ingest_source(url, source, repository, http_client=second_client, **options)

    assert first["status"] == "ingested"
    assert duplicate["status"] == "skipped_duplicate"
    assert duplicate["storage"] == "unchanged"
    assert repository.chunks == original_chunks


def test_web_ingestion_rejects_reused_source_id_with_different_url() -> None:
    import httpx

    original_url = "https://docs.example/original.pdf"
    repository = InMemoryChunkRepository()
    initial_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=make_text_pdf("Sugarcane crop management and varieties."),
            )
        )
    )
    source = metadata(source_id="stable-sugarcane", source_uri=original_url)
    options = {
        "trusted_publishers": ["Agriculture Department"],
        "trusted_domains": ["docs.example"],
        "max_download_bytes": 1024 * 1024,
        "embedding_api_key": "",
        "embedding_model": "unused-in-test",
        "embedding_dimension": 64,
        "resolver": lambda _host, _port: ["8.8.8.8"],
        "embedding_provider": HashEmbeddingProvider(),
    }
    ingest_source(original_url, source, repository, http_client=initial_client, **options)

    with pytest.raises(ValueError, match="different provenance"):
        ingest_source(
            "https://docs.example/changed.pdf",
            metadata(source_id="stable-sugarcane", source_uri="https://docs.example/changed.pdf"),
            repository,
            http_client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda _request: pytest.fail("conflicting source ID must not be downloaded")
                )
            ),
            **options,
        )


def test_local_file_ingestion_still_uses_existing_pipeline(tmp_path) -> None:
    file_path = tmp_path / "guide.txt"
    file_path.write_text("Sugarcane local agricultural guidance.", encoding="utf-8")
    repository = InMemoryChunkRepository()

    report = ingest_source(
        str(file_path),
        metadata(source_id="local-guide", publisher="Agriculture Department"),
        repository,
        ["Agriculture Department"],
        [],
        1024,
        "",
        "unused-in-test",
        64,
        embedding_provider=HashEmbeddingProvider(),
    )

    assert report["status"] == "ingested"
    assert report["source_url"] is None
    assert repository.chunks[0].text == "Sugarcane local agricultural guidance."


def test_web_ingestion_rejects_unapproved_publisher_before_download() -> None:
    import httpx

    url = "https://docs.example/sugarcane.pdf"
    repository = InMemoryChunkRepository()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("unapproved publisher must not trigger a request")
        )
    )

    with pytest.raises(ValueError, match="RAG_TRUSTED_PUBLISHERS"):
        ingest_source(
            url,
            metadata(source_uri=url, publisher="Unapproved University"),
            repository,
            ["Agriculture Department"],
            ["docs.example"],
            1024,
            "",
            "unused-in-test",
            64,
            http_client=client,
            resolver=lambda _host, _port: ["8.8.8.8"],
            embedding_provider=HashEmbeddingProvider(),
        )


def test_pdf_extraction_rejects_empty_scanned_and_unsupported_documents() -> None:
    with pytest.raises(ValueError, match="empty or scanned"):
        extract_text(make_text_pdf(None), "application/pdf")
    with pytest.raises(ValueError, match="plain text, HTML, and PDF"):
        extract_text(b"unsupported", "application/octet-stream")


def test_html_extraction_ignores_scripts_styles_and_noscript_content() -> None:
    html = (
        b"<html><head><title>Guide</title><script>tracking data</script>"
        b"<style>hidden styles</style></head><body>Verified advice"
        b"<noscript>fallback navigation</noscript></body></html>"
    )

    assert extract_text(html, "text/html") == "Guide Verified advice"


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


def test_retrieval_isolates_embeddings_by_provider_and_model() -> None:
    from uuid import uuid4

    from app.rag.types import DocumentChunk

    repository = InMemoryChunkRepository()
    for source_id, provider_name, model_name in (
        ("gemini-doc", "gemini", "gemini-embedding-001"),
        ("alibaba-doc", "alibaba", "text-embedding-v4"),
    ):
        source = metadata(
            source_id=source_id,
            embedding_provider=provider_name,
            embedding_model=model_name,
        )
        repository.add_many(
            [
                DocumentChunk(
                    uuid4(),
                    uuid4(),
                    "Sugarcane agricultural guidance.",
                    source,
                    0,
                    (1.0, 0.0),
                )
            ]
        )

    class TestProvider:
        dimension = 2

        def __init__(self, provider_name: str, model_name: str) -> None:
            self.provider_name = provider_name
            self.model_name = model_name

        def embed(self, _text: str, *, task_type: str = "RETRIEVAL_QUERY") -> tuple[float, ...]:
            return (1.0, 0.0)

    gemini_results = RetrievalService(
        repository, TestProvider("gemini", "gemini-embedding-001")
    ).retrieve("sugarcane")
    alibaba_results = RetrievalService(
        repository, TestProvider("alibaba", "text-embedding-v4")
    ).retrieve("sugarcane")

    assert [item.chunk.metadata.source_id for item in gemini_results] == ["gemini-doc"]
    assert [item.chunk.metadata.source_id for item in alibaba_results] == ["alibaba-doc"]


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


def test_pgvector_search_probes_all_ivfflat_lists() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.all.return_value = []
    repository = PgVectorChunkRepository(engine)

    repository.search((0.0,) * 1536, 5)

    assert str(connection.execute.call_args_list[0].args[0]) == (
        "SET LOCAL ivfflat.probes = 10"
    )


def test_pgvector_search_filters_by_embedding_provider_and_model() -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.all.return_value = []
    repository = PgVectorChunkRepository(engine)

    repository.search(
        (0.0,) * 1536,
        5,
        RetrievalFilter(
            embedding_provider="alibaba",
            embedding_model="text-embedding-v4",
        ),
    )

    query = connection.execute.call_args_list[1].args[0]
    parameters = connection.execute.call_args_list[1].args[1]
    assert "COALESCE(metadata ->> 'embedding_provider', :legacy_embedding_provider)" in str(
        query
    )
    assert "COALESCE(metadata ->> 'embedding_model', :legacy_embedding_model)" in str(query)
    assert parameters["embedding_provider"] == "alibaba"
    assert parameters["embedding_model"] == "text-embedding-v4"


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
