# Agricultural Retrieval-Augmented Generation

## Purpose

WeatherGPT's agricultural knowledge layer retrieves guidance from explicitly trusted
documents before any LLM explanation. Its operator-only ingestion CLI can fetch documents
only from an explicit HTTPS host allowlist; it does not browse arbitrary pages or treat
random online content as authoritative.

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
   embeddings. `AlibabaEmbeddingProvider` uses Alibaba Cloud Model Studio's
   OpenAI-compatible `/embeddings` API, `DASHSCOPE_API_KEY`, and `text-embedding-v4`.
   Select it with `EMBEDDING_PROVIDER=alibaba` and configure the workspace/region API
   endpoint in `DASHSCOPE_BASE_URL`. `CohereEmbeddingProvider` uses Cohere's `/v2/embed`
   API, `COHERE_API_KEY`, and the `embed-v4.0` model. Set
   `EMBEDDING_PROVIDER=cohere` to select it; it uses `search_document` during ingestion
   and `search_query` for questions. Ingestion and query paths use the same provider factory.
   The pgvector migration is fixed at 1536 dimensions, so `RAG_EMBEDDING_DIMENSION`
   must remain 1536. `HashEmbeddingProvider` is only
   deterministic test scaffolding. Document ingestion uses each provider's batch API and
   preserves source chunk order; query embeddings use the same selected provider and model.
   Gemini HTTP 429 responses honor the retry delay and activate a process-wide cooldown for
   that model/key combination.
5. `postgres.py` stores embeddings in PostgreSQL `pgvector` and filters metadata in SQL.
6. `retrieval.py` applies query embedding, metadata filters, score thresholds, and emits
   source-bearing context for an LLM.

## Trusted-source policy

Ingestion requires both `metadata.trusted == true` and an exact publisher match in
`RAG_TRUSTED_PUBLISHERS`. URL ingestion additionally requires an exact host match in
`RAG_TRUSTED_DOMAINS`, HTTPS on port 443, public DNS results, safe redirects, a supported
PDF/HTML content type and format, and a response within `RAG_WEB_MAX_DOWNLOAD_BYTES`.
Redirects are revalidated before the next request. The downloader does not use ambient
proxy settings. Operators must supply the publisher, title, publication date, language,
document type, and source identifier; the original URL is retained as provenance.

## PostgreSQL and pgvector

Migration `20260910_0005_agricultural_rag.py` enables the PostgreSQL `vector` extension
and creates `agricultural_document_chunks` with a `vector(1536)` embedding column and an
IVFFlat cosine index. The production embedding model must therefore emit 1536 dimensions,
or the migration and model configuration must be changed together. Apply migrations only
on PostgreSQL instances where the pgvector extension is installed and permitted.

The in-memory repository is used for unit tests and local logic verification. It is not a
replacement for production vector storage.

Each chunk records its embedding provider and model in its existing JSON metadata. Vector
search filters on both fields, so switching to Alibaba does not compare Alibaba query
vectors against old Gemini vectors. Existing Gemini rows are not changed or deleted and
continue to be searchable when Gemini is selected. Re-ingest documents to create vectors
for the selected provider; re-ingestion replaces the existing chunks for that document.
Do not run two embedding-provider configurations against the same collection concurrently.

## Local setup and ingestion

Configure `GEMINI_API_KEY` and an exact JSON list of approved publishers in
`RAG_TRUSTED_PUBLISHERS`, for example `RAG_TRUSTED_PUBLISHERS=["Agriculture Department"]`.
For Alibaba embeddings, set `EMBEDDING_PROVIDER=alibaba`, `DASHSCOPE_API_KEY`, and
`DASHSCOPE_BASE_URL` to the compatible endpoint for the workspace and region. For Cohere,
set `EMBEDDING_PROVIDER=cohere` and `COHERE_API_KEY`. No SDK dependency is required.
Set `RAG_MINIMUM_SCORE` after evaluating a small set of representative query/document
pairs; production startup rejects the development default of zero. The score is cosine
similarity and should be calibrated against the chosen embedding model and corpus.

From the `backend/` directory, run the operator-only CLI against a local UTF-8 `.txt`,
`.html`, or text-based `.pdf` file, or an allowlisted HTTPS PDF/HTML URL:

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

For URL ingestion, use the URL as the positional source instead of a local path; the CLI
records it as `source_uri`. The publisher must exactly match the configured allowlist.
The CLI emits a JSON status with extracted-text length, chunk count, embedding count, and
storage result. A repeated URL source ID is skipped without replacing existing chunks.
Reusing a source ID with a local file retains the previous replacement behavior. Ingestion
and query paths use the same embedding model configuration.

## LLM boundary

The retrieval service returns text plus source metadata. The conversational integration
passes filtered excerpts and source metadata to Gemini for knowledge-based claims and
requires citations. When no result clears `RAG_MINIMUM_SCORE`, the assistant must say
verified agricultural guidance was not found rather than inventing an answer.

The RAG layer does not make irrigation, spraying, sowing, or risk decisions. Those remain
in the deterministic Agricultural Decision Engine.
