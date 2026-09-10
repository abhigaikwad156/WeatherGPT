# WeatherGPT: Technical Architecture and Implementation Plan

## 1. Purpose and scope

WeatherGPT is an agricultural weather decision-support system for farmers. It turns weather, farm, crop, and agricultural-knowledge inputs into traceable recommendations in the farmer's preferred language.

The core safety boundary is:

```text
User -> Intent Understanding -> Data and Tools -> Decision Engine -> RAG -> LLM Explanation -> Response
```

An LLM may classify a request, help retrieve knowledge, and explain a result. It must never be the authority that creates weather or agricultural recommendations. Every actionable answer must be grounded in deterministic decision output, retrieved data, and, when applicable, cited knowledge.

This first plan intentionally does not implement product features.

## 2. Architectural goals

- Provide reliable, explainable field-level recommendations.
- Support Marathi first, with a language-neutral internal domain model.
- Isolate external providers (weather, LLM, messaging) behind interfaces.
- Preserve provenance: which forecast, farm data, policy version, and knowledge sources produced an answer.
- Start with simple rules and transparent calculations; introduce ML only after data and evaluation are available.
- Keep the initial deployment small enough for a BTech project while retaining production-quality boundaries.

## 3. Target system architecture

```text
React web client
  |-- REST: authentication, farms, crops, conversations, recommendations
  |-- WebSocket: alerts and job-status updates
  v
FastAPI application
  |-- API / auth / validation / request logging
  |-- application services (orchestration and transactions)
  |-- domain layer (decision models, rules, policies)
  |-- adapters
       |-- PostgreSQL + PostGIS + pgvector
       |-- Redis
       |-- weather provider
       |-- LLM provider
       |-- embedding provider
       `-- notification provider (later)
  v
Background worker (scheduled forecast refreshes and alert evaluation)
```

The backend should initially run as a modular monolith. API, worker, and scheduled jobs can share the same domain and application packages while being separately deployable containers. Microservices are not needed initially.

## 4. Repository layout to introduce incrementally

```text
WeatherGPT/
  frontend/                 # React + TypeScript application
  backend/
    app/
      api/                  # FastAPI routers, request/response schemas
      application/          # use cases and orchestration services
      domain/               # entities, value objects, decisions, policies
      infrastructure/       # database, provider adapters, cache, logging
      workers/              # scheduled/background job entry points
      main.py
    tests/
      unit/
      integration/
    alembic/
  docs/
    adr/                    # architecture decision records
  infra/                    # Docker and local deployment configuration
  docker-compose.yml
  .env.example
  README.md
```

The final layout may be adjusted only after the initial scaffold is reviewed. Feature code should depend inward: `api -> application -> domain`; infrastructure implements interfaces defined by the domain/application layers.

## 5. Core backend domains

| Domain | Responsibility | Initial source of truth |
| --- | --- | --- |
| Identity | users, JWT sessions, roles | PostgreSQL |
| Farmer profile | preferred language, contact and preferences | PostgreSQL |
| Farm | farm boundary/point, soil profile, irrigation capability | PostgreSQL + PostGIS |
| Crop cycle | crop, variety, sowing/transplant date, growth stage | PostgreSQL |
| Weather | current, forecast, historical observations and provenance | weather adapter + PostgreSQL cache |
| Conversation | user message, parsed intent, response and source trace | PostgreSQL |
| Recommendation | deterministic action, confidence/limitations, evidence | PostgreSQL |
| Agricultural knowledge | curated documents and chunk embeddings | PostgreSQL + pgvector |
| Alerts | evaluated weather/crop risk and delivery state | PostgreSQL + Redis/worker |

### Key initial data entities

- `User`, `FarmerProfile`, `Farm`, `Field`, `SoilProfile`
- `Crop`, `CropCycle`, `GrowthStage`
- `WeatherSnapshot`, `WeatherForecast`, `WeatherProviderRequest`
- `Conversation`, `Message`, `IntentParse`
- `Recommendation`, `DecisionEvidence`, `DecisionPolicyVersion`
- `KnowledgeDocument`, `KnowledgeChunk`, `KnowledgeCitation`
- `AlertRule`, `AlertEvent`, `AlertDelivery`

Locations should be stored as PostGIS geography values and exposed through validated latitude/longitude or GeoJSON request schemas. Do not store farm location only as unvalidated text.

## 6. Recommendation request flow

For a question such as “Should I irrigate my onion crop today?”, the orchestration service should:

1. Authenticate the user and load their language preference.
2. Parse the message into a constrained intent schema (for example: `irrigation_advice`, crop reference, farm/field reference, date).
3. Resolve missing entities from the farmer profile and ask a focused follow-up when essential data is unavailable.
4. Fetch cached/weather-provider observations and forecast for the field location.
5. Load the crop cycle, growth stage, soil, and irrigation information.
6. Execute a versioned deterministic irrigation decision policy.
7. Retrieve agricultural knowledge only when policy context, guidance, or safety caveats are required.
8. Give the LLM a structured, non-authoritative explanation contract containing the decision result and allowed evidence.
9. Validate the generated response against the decision result, persist the provenance, and return it in the preferred language.

If weather data is stale, farm data is insufficient, a provider fails, or the policy cannot make a safe recommendation, the response must explicitly say so and avoid an instruction that could be mistaken for advice.

## 7. Decision engine design

The initial decision engine should be Python code with typed inputs and versioned rules, not an LLM prompt and not an ML model.

Example irrigation inputs:

- crop and growth stage
- field soil characteristics and available moisture, if known
- irrigation type/capacity
- recent rainfall
- forecast precipitation, temperature, wind, and evapotranspiration when available
- local policy thresholds and data freshness

Example outputs:

```json
{
  "status": "recommend_irrigation",
  "recommended_window": "today_morning",
  "reason_codes": ["soil_moisture_below_threshold", "low_rain_probability"],
  "limitations": ["soil_moisture_is_estimated"],
  "policy_version": "irrigation-v1",
  "evidence": []
}
```

Rules must be unit-tested using representative weather and crop cases. Policies should be configurable through validated files or database records only after a simple code-based version has been proven.

## 8. AI and RAG boundaries

### Intent understanding

Use a provider-agnostic `LanguageModelClient` interface that returns a validated Pydantic schema. A deterministic keyword/command parser can be a fallback for narrow initial intents. Parsed values are untrusted until matched to known farm/crop records.

### RAG

Curated agricultural material is ingested with document metadata such as crop, region, source, publication date, language, and review status. Chunks are embedded and stored through pgvector. Retrieval filters by crop/region where possible and returns citations.

RAG supplies supporting explanation and safety information; it does not override decision-engine output. Initial knowledge sources must be identified and licensed before ingestion, with an explicit review process.

### LLM explanation

The LLM receives only structured facts: the validated intent, decision output, data freshness, and retrieved citations. It must return a schema such as `summary`, `rationale`, `actions`, `caveats`, and `citations`. Server-side validation prevents it from changing the recommendation status, fabricating numeric weather facts, or presenting uncited agronomic claims.

## 9. External integrations and resilience

Define provider protocols before selecting a vendor:

- `WeatherProvider`: current weather, hourly/daily forecast, historical data
- `LanguageModelClient`: structured extraction and constrained explanation
- `EmbeddingClient`: document/query embeddings
- `NotificationProvider`: alert delivery (future phase)

Each adapter must have timeouts, typed provider errors, retry rules appropriate to idempotency, structured logs, and a mock implementation for tests/local development. API keys live only in environment variables and are excluded from source control.

Redis should cache weather results by normalized location/time window, rate-limit expensive endpoints, and support background job coordination. PostgreSQL remains the durable source of truth.

## 10. Security, privacy, and observability

- JWT access tokens with secure password hashing and explicit token expiration.
- Role model beginning with farmer and administrator; authorization is enforced at service boundaries.
- Validate all external input with Pydantic and maintain an allowlist for LLM tool/data access.
- Do not place secrets, raw passwords, or sensitive farmer details in application logs.
- Structured logs include request/correlation IDs, provider latency, and decision-policy version.
- Persist data provenance and response/decision audit information.
- Add health and readiness endpoints that check configured dependencies without exposing secrets.

## 11. Testing strategy

- Unit tests: domain rules, intent schema validation, provider adapters with mocks, and authorization rules.
- Integration tests: FastAPI endpoints against disposable PostgreSQL/Redis services and migration verification.
- Contract tests: weather and LLM adapter response normalization.
- Frontend tests: component behavior, form validation, API-client error states.
- End-to-end tests later: user registration, farm setup, recommendation request, and alert display.
- Test fixtures must use synthetic farm data and mocked weather/LLM responses unless explicit non-production provider tests are enabled.

## 12. Incremental implementation roadmap

### Phase 0 — Repository foundation

Create the monorepo layout, backend and frontend toolchains, Docker Compose for PostgreSQL/PostGIS and Redis, environment templates, linting, formatting, CI baseline, and health endpoint. No agricultural recommendation logic.

### Phase 1 — Identity and farm profile

Implement JWT authentication, farmer profile, farm/field CRUD, validated geospatial storage, crop-cycle records, migrations, and API tests. Frontend provides secure sign-in and farm/crop data entry.

### Phase 2 — Weather abstraction and data access

Implement the `WeatherProvider` interface, mock provider, one selected real provider adapter, caching, weather persistence/provenance, and endpoints that expose data freshness. No LLM use.

### Phase 3 — First deterministic agricultural decision

Implement an irrigation recommendation policy for a deliberately narrow crop/stage scope, with explainable reason codes, data-insufficiency handling, test cases, and a farmer-facing recommendation endpoint. Confirm agronomy thresholds with a qualified source/advisor before representing them as production guidance.

### Phase 4 — Conversational orchestration

Implement conversations, constrained intent extraction, entity resolution, the orchestrated request flow, and Marathi response support. The result must be based exclusively on the Phase 3 decision output.

### Phase 5 — Curated RAG and grounded explanation

Add document ingestion, pgvector retrieval, citations, review metadata, and provider-agnostic LLM explanation with structured output validation.

### Phase 6 — Alerts and real-time delivery

Add scheduled weather refresh/evaluation, versioned alert rules, deduplication, WebSocket notifications, delivery audit records, and a frontend alerts center.

### Phase 7 — ML-assisted enhancements

Only after collecting suitable, consented data: create offline datasets, baselines, evaluation metrics, model-version tracking, and human-reviewed rollout. ML predictions remain inputs to decision policy, never undocumented replacements for it.

### Phase 8 — Production hardening

Complete CI/CD, backup/restore procedures, monitoring, rate limiting, security review, API documentation, data retention policy, load tests, and deployment runbooks.

## 13. Initial acceptance criteria for Phase 0

- A developer can start all local dependencies with Docker Compose.
- Backend exposes documented health/readiness endpoints and passes lint/type/test checks.
- Frontend starts and has its own lint/test commands.
- Secrets are supplied through `.env` files and `.env.example` contains placeholders only.
- PostgreSQL uses PostGIS and pgvector extensions through a migration/init process.
- The repository contains concise setup and architecture documentation.

## 14. Architecture decisions to record as ADRs

1. Modular monolith before microservices.
2. PostgreSQL/PostGIS/pgvector as the initial consolidated data platform.
3. Deterministic, versioned policies as recommendation authority.
4. Provider abstractions for weather, LLMs, embeddings, and notifications.
5. Structured LLM output and server-side verification.
6. Marathi-first user experience with language-neutral internal data.

Each decision should be captured when it is implemented, including context, alternatives, consequences, and review date.
