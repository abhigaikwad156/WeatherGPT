"""Operator CLI for ingesting trusted agricultural guidance into pgvector."""

import argparse
import json
import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.infrastructure.database import engine
from app.rag.embeddings import EmbeddingProvider, GeminiEmbeddingProvider, create_embedding_provider
from app.rag.extract import extract_text
from app.rag.ingestion import DocumentIngestionService
from app.rag.postgres import PgVectorChunkRepository
from app.rag.repository import ChunkRepository
from app.rag.types import SourceMetadata
from app.rag.web import fetch_web_document


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Local document path or trusted HTTPS PDF/HTML URL")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--document-type", default="guidance")
    parser.add_argument("--language", default="en")
    parser.add_argument("--publication-date")
    parser.add_argument("--source-uri")
    arguments = parser.parse_args(argv)

    settings = get_settings()
    source_is_url = arguments.source.lower().startswith(("http://", "https://"))
    source_uri = arguments.source if source_is_url else arguments.source_uri
    if source_is_url and arguments.source_uri and arguments.source_uri != arguments.source:
        parser.error("--source-uri must match the supplied document URL")
    metadata = SourceMetadata(
        source_id=arguments.source_id,
        title=arguments.title,
        publisher=arguments.publisher,
        source_uri=source_uri,
        publication_date=arguments.publication_date,
        language=arguments.language,
        document_type=arguments.document_type,
        trusted=arguments.publisher in settings.rag_trusted_publishers,
    )
    repository = PgVectorChunkRepository(engine)
    try:
        report = ingest_source(
            arguments.source,
            metadata,
            repository,
            settings.rag_trusted_publishers,
            settings.rag_trusted_domains,
            settings.rag_web_max_download_bytes,
            settings.gemini_api_key or "",
            settings.rag_embedding_model,
            settings.rag_embedding_dimension,
            embedding_provider=create_embedding_provider(settings),
        )
    except (OSError, RuntimeError, SQLAlchemyError, ValueError, httpx.HTTPError) as error:
        report = {
            "status": "failed",
            "source_id": metadata.source_id,
            "source_url": metadata.source_uri,
            "title": metadata.title,
            "publisher": metadata.publisher,
            "document_type": metadata.document_type,
            "language": metadata.language,
            "publication_date": metadata.publication_date,
            "extracted_text_length": None,
            "chunk_count": None,
            "embeddings_stored": 0,
            "storage": "not_stored",
            "error": str(error),
        }
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] == "failed":
        raise SystemExit(1)


def ingest_source(
    source: str,
    metadata: SourceMetadata,
    repository: ChunkRepository,
    trusted_publishers: list[str],
    trusted_domains: list[str],
    max_download_bytes: int,
    embedding_api_key: str,
    embedding_model: str,
    embedding_dimension: int,
    *,
    http_client: httpx.Client | None = None,
    resolver: Callable[[str, int], Iterable[str]] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, object]:
    """Ingest one local or remote source, leaving duplicate content untouched."""
    base_report: dict[str, object] = {
        "source_id": metadata.source_id,
        "source_url": metadata.source_uri,
        "title": metadata.title,
        "publisher": metadata.publisher,
        "document_type": metadata.document_type,
        "language": metadata.language,
        "publication_date": metadata.publication_date,
    }
    if not metadata.trusted or metadata.publisher not in trusted_publishers:
        raise ValueError(
            f"publisher {metadata.publisher!r} is not approved in RAG_TRUSTED_PUBLISHERS"
        )
    is_url = source.lower().startswith(("http://", "https://"))
    if is_url and repository.has_source_id(metadata.source_id):
        if repository.source_uri_for_id(metadata.source_id) != metadata.source_uri:
            raise ValueError(
                f"source ID {metadata.source_id!r} already exists with different provenance"
            )
        return {
            "status": "skipped_duplicate",
            **base_report,
            "extracted_text_length": None,
            "chunk_count": 0,
            "embeddings_stored": 0,
            "storage": "unchanged",
        }

    if is_url:
        if metadata.source_uri != source:
            raise ValueError("Source metadata URL must match the supplied document URL")
        document = fetch_web_document(
            source,
            trusted_domains,
            max_download_bytes,
            client=http_client,
            resolver=resolver,
        )
        content, mime_type = document.content, document.mime_type
    else:
        source_path = Path(source)
        if not source_path.is_file():
            raise ValueError(f"document file does not exist: {source_path}")
        mime_type, _ = mimetypes.guess_type(source_path.name)
        if mime_type not in {
            "application/pdf",
            "application/xhtml+xml",
            "text/html",
            "text/plain",
        }:
            raise ValueError("only UTF-8 .txt/.html and text-based .pdf files are supported")
        content = source_path.read_bytes()

    extracted_text = extract_text(content, mime_type)
    provider = embedding_provider or GeminiEmbeddingProvider(
        embedding_api_key,
        embedding_model,
        embedding_dimension,
    )
    service = DocumentIngestionService(repository, provider, trusted_publishers)
    progress = {"chunk_count": None, "embeddings_stored": 0, "storage": "not_stored"}

    def update_progress(stage: str, count: int) -> None:
        if stage == "chunks":
            progress["chunk_count"] = count
        elif stage == "embeddings":
            progress["embeddings_stored"] = count
        elif stage == "stored":
            progress["storage"] = "stored"

    try:
        chunks = service.ingest(content, mime_type, metadata, on_progress=update_progress)
    except (RuntimeError, SQLAlchemyError, ValueError) as error:
        return {
            "status": "failed",
            **base_report,
            "extracted_text_length": len(extracted_text),
            **progress,
            "error": str(error),
        }
    return {
        "status": "ingested",
        **base_report,
        "extracted_text_length": len(extracted_text),
        "chunk_count": len(chunks),
        "embeddings_stored": sum(chunk.embedding is not None for chunk in chunks),
        "storage": "stored",
    }


if __name__ == "__main__":
    main()