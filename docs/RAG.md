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

1. `extract.py` accepts UTF-8 plain text, HTML, and text-based PDFs using local extraction.
   It performs no network access and rejects empty/scanned PDFs without extractable text.
2. `chunking.py` creates deterministic overlapping chunks.
3. `types.py` carries source metadata on every document and chunk.
4. `embeddings.py` defines the embedding-provider contract. `GeminiEmbeddingProvider`
   uses `GEMINI_API_KEY` and `RAG_EMBEDDING_MODEL` for semantic query and document
   embeddings. The pgvector migration is fixed at 1536 dimensions, so
   `RAG_EMBEDDING_DIMENSION` must remain 1536. `HashEmbeddingProvider` is only
   deterministic test scaffolding. Document ingestion uses Gemini's synchronous
   `batchEmbedContents` endpoint in batches of 16, preserving source chunk order; query
   embeddings remain single-query requests. HTTP 429 responses honor Gemini's retry delay
   and activate a process-wide cooldown for that model/key combination.
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

## Local setup and ingestion

Configure `GEMINI_API_KEY` and an exact JSON list of approved publishers in
`RAG_TRUSTED_PUBLISHERS`, for example `RAG_TRUSTED_PUBLISHERS=["Agriculture Department"]`.
Set `RAG_MINIMUM_SCORE` after evaluating a small set of representative query/document
pairs; production startup rejects the development default of zero. The score is cosine
similarity and should be calibrated against the chosen embedding model and corpus.

From the `backend/` directory, run the operator-only CLI against a local UTF-8 `.txt`,
`.html`, or text-based `.pdf` file:

```powershell
python -m app.rag.ingest_cli .\approved\irrigation-guide.txt `
   --source-id guide-2026-01 `
   --title "Reviewed irrigation guide" `
   --publisher "Agriculture Department" `
   --document-type irrigation `
   --language en `
   --publication-date 2026-01-15 `
   --source-uri https://example.org/guide
```

The publisher must exactly match the allowlist. The CLI does not download the URI. Reusing
a source ID replaces that document's chunks, so approved updates do not leave old chunks
behind. Ingestion and query paths use the same embedding model configuration.

## LLM boundary

The retrieval service returns text plus source metadata. The conversational integration
passes filtered excerpts and source metadata to Gemini for knowledge-based claims and
requires citations. When no result clears `RAG_MINIMUM_SCORE`, the assistant must say
verified agricultural guidance was not found rather than inventing an answer.

The RAG layer does not make irrigation, spraying, sowing, or risk decisions. Those remain
in the deterministic Agricultural Decision Engine.
