# Agricultural Retrieval-Augmented Generation

## Purpose

WeatherGPT's agricultural knowledge layer retrieves guidance from explicitly trusted
documents before any LLM explanation. It does not browse the internet, scrape arbitrary
pages, or treat random online content as authoritative.

Supported document categories include crop cultivation guides, government advisories,
weather guidance, disaster preparedness, irrigation guidance, and spraying guidance.

## Pipeline

`Document -> extraction -> chunking -> metadata -> embeddings -> vector storage -> retrieval -> context filtering -> LLM`

The implementation is in [`backend/app/rag/`](../backend/app/rag/):

1. `extract.py` accepts UTF-8 plain text and HTML only. It performs no network access.
2. `chunking.py` creates deterministic overlapping chunks.
3. `types.py` carries source metadata on every document and chunk.
4. `embeddings.py` defines the embedding-provider contract. `HashEmbeddingProvider` is
   deterministic test/development scaffolding, not a semantic production model.
5. `postgres.py` stores embeddings in PostgreSQL `pgvector` and filters metadata in SQL.
6. `retrieval.py` applies query embedding, metadata filters, score thresholds, and emits
   source-bearing context for an LLM.

## Trusted-source policy

Ingestion requires both `metadata.trusted == true` and an exact publisher match in the
configured allowlist. A source URI is metadata only; the ingestion service never fetches
it. Operators must acquire documents through an approved process and record publisher,
title, publication date, language, document type, and source identifier.

## PostgreSQL and pgvector

Migration `20260910_0005_agricultural_rag.py` enables the PostgreSQL `vector` extension
and creates `agricultural_document_chunks` with a `vector(1536)` embedding column and an
IVFFlat cosine index. The production embedding model must therefore emit 1536 dimensions,
or the migration and model configuration must be changed together. Apply migrations only
on PostgreSQL instances where the pgvector extension is installed and permitted.

The in-memory repository is used for unit tests and local logic verification. It is not a
replacement for production vector storage.

## LLM boundary

The retrieval service returns text plus source metadata. An LLM integration must receive
only this filtered context for knowledge-based claims and must cite the returned source
metadata. If retrieval returns no acceptable context, the assistant should say that
verified agricultural guidance was not found rather than inventing an answer.

The RAG layer does not make irrigation, spraying, sowing, or risk decisions. Those remain
in the deterministic Agricultural Decision Engine.
