"""Operator CLI for ingesting trusted agricultural guidance into pgvector."""

import argparse
import mimetypes
from pathlib import Path

from app.core.config import get_settings
from app.infrastructure.database import engine
from app.rag.embeddings import GeminiEmbeddingProvider
from app.rag.ingestion import DocumentIngestionService
from app.rag.postgres import PgVectorChunkRepository
from app.rag.types import SourceMetadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file", type=Path, help="Local UTF-8 .txt/.html or text-based .pdf file"
    )
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--document-type", default="guidance")
    parser.add_argument("--language", default="en")
    parser.add_argument("--publication-date")
    parser.add_argument("--source-uri")
    arguments = parser.parse_args()

    settings = get_settings()
    if arguments.publisher not in settings.rag_trusted_publishers:
        parser.error(
            "publisher is not in RAG_TRUSTED_PUBLISHERS; configure the exact approved publisher"
        )
    if not arguments.file.is_file():
        parser.error(f"document file does not exist: {arguments.file}")

    mime_type, _ = mimetypes.guess_type(arguments.file.name)
    if mime_type not in {"text/plain", "text/html", "application/xhtml+xml", "application/pdf"}:
        parser.error("only UTF-8 .txt, .html, and text-based .pdf files are supported")
    metadata = SourceMetadata(
        source_id=arguments.source_id,
        title=arguments.title,
        publisher=arguments.publisher,
        source_uri=arguments.source_uri,
        publication_date=arguments.publication_date,
        language=arguments.language,
        document_type=arguments.document_type,
        trusted=True,
    )
    service = DocumentIngestionService(
        PgVectorChunkRepository(engine),
        GeminiEmbeddingProvider(
            settings.gemini_api_key or "",
            settings.rag_embedding_model,
            settings.rag_embedding_dimension,
        ),
        settings.rag_trusted_publishers,
    )
    chunks = service.ingest(arguments.file.read_bytes(), mime_type, metadata)
    print(f"Ingested {len(chunks)} chunks from {metadata.title!r} ({metadata.source_id}).")


if __name__ == "__main__":
    main()