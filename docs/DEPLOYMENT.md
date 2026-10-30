# Public deployment

This is the tested deployment shape for the current application:

```text
Browser -> Vercel (React SPA) -> Render (FastAPI) -> Neon (Postgres + PostGIS + pgvector)
                                                    -> Upstash (Redis cache)
```

It preserves the existing API, JWT authentication, database ownership checks, decision rules,
weather-provider code, and AI/RAG safeguards. No credentials belong in this repository.

## Important limitations and launch blockers

- A full production configuration is deliberately rejected unless `GEMINI_API_KEY`, a positive
  `RAG_MINIMUM_SCORE`, and a non-empty `RAG_TRUSTED_PUBLISHERS` list are supplied. Use values
  reviewed for this application; do not bypass these safeguards with placeholder values.
- `GET /api/v1/health` is a *liveness* endpoint. It does not query Postgres or Redis, so a green
  Render health check does not prove database connectivity. The migration command and the manual
  checks below cover that separately.
- The free Render web service sleeps after 15 minutes without traffic and can take about a minute
  to wake. It also has a monthly usage cap. This is suitable for a public demo, not a reliability
  promise.
- Free Neon and Upstash plans have usage limits. Monitor their dashboards. The current RAG schema
  stores 1536-dimension vectors, so document ingestion can consume the 1 GB free database limit.
- OpenWeather requires an API key from the deployment owner. Nominatim requires a deployment-specific
  identifying user agent with a monitored contact method. Follow each provider's usage policy.

## 1. Provision data services

### Neon PostgreSQL (free)

1. Create a Neon project in a region near the Render service.
2. Copy the **pooled** connection string and convert its scheme for SQLAlchemy:

   ```text
   postgresql://USER:PASSWORD@HOST/DB?sslmode=require
   ```

   becomes:

   ```text
   postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
   ```

3. In Neon SQL Editor, enable and verify the required extensions. These commands are idempotent:

   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS vector;
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'vector');
   ```

   The Alembic migrations repeat the first two commands, but doing this first makes extension
   permission problems visible before deployment.

### Upstash Redis (free)

1. Create a Redis database in a region close to Render.
2. Copy the **TCP** connection string, which has the `rediss://` scheme. Set it as `REDIS_URL`.
   The existing `redis` Python client accepts this URL and enables TLS from the scheme.

## 2. Deploy the FastAPI service on Render

The root [render.yaml](../render.yaml) describes the service. In Render, select **New → Blueprint**
and point it at the repository, or create a Web Service manually with these exact settings:

| Setting | Value |
| --- | --- |
| Runtime | Python 3.12 (`backend/.python-version`) |
| Root directory | `backend` |
| Build command | `pip install --upgrade pip && pip install .` |
| Start command | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/v1/health` |
| Instance type | Free (for a demo) |

Set these environment variables in the Render dashboard. Values marked **secret** must be entered
only in the dashboard, never committed or pasted into chat.

| Variable | Required value / source |
| --- | --- |
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `DATABASE_URL` | **secret**: converted Neon pooled URL above |
| `REDIS_URL` | **secret**: Upstash TCP `rediss://` URL |
| `JWT_SECRET_KEY` | **secret**: a new random value of at least 32 characters |
| `CORS_ORIGINS` | JSON list with the exact Vercel origin, e.g. `["https://your-project.vercel.app"]` |
| `WEATHER_PROVIDER` | `openweather` |
| `OPENWEATHER_API_KEY` | **secret**: an active OpenWeather API key controlled by the project owner |
| `WEATHER_API_TIMEOUT_SECONDS` | `5` |
| `WEATHER_API_RETRIES` | `2` |
| `WEATHER_CACHE_TTL_SECONDS` | `300` |
| `NOMINATIM_BASE_URL` | `https://nominatim.openstreetmap.org` |
| `NOMINATIM_USER_AGENT` | an identifying product/version plus monitored contact address or URL |
| `NOMINATIM_TIMEOUT_SECONDS` | `5` |
| `GEMINI_API_KEY` | **secret**: an active key controlled by the project owner |
| `GEMINI_MODEL` | the reviewed model name available to that key |
| `RAG_EMBEDDING_MODEL` | the reviewed embedding model that emits 1536 dimensions |
| `RAG_EMBEDDING_DIMENSION` | `1536` |
| `RAG_MINIMUM_SCORE` | a previously calibrated, positive score |
| `RAG_TRUSTED_PUBLISHERS` | JSON list of approved sources, e.g. `["publisher.example"]` — use real reviewed publishers only |

The OpenWeather provider calls `https://api.openweathermap.org/data/2.5/weather` and
`https://api.openweathermap.org/data/2.5/forecast` with `units=metric`. The free forecast supplies
up to 5 days at 3-hour intervals; the API does not claim a 7-day forecast or invent unavailable
precipitation probabilities. If you select `external`, set a vendor-specific `WEATHER_API_URL` and
**secret** `WEATHER_API_KEY` and verify that its response matches the application's normalized
provider contract.

The start command runs `alembic upgrade head` before the web server. It only applies forward
migrations and does not call a downgrade or delete existing data. Before applying it to any existing
database, review the pending migration with `alembic current` and `alembic history` from `backend`.

After deployment, record the Render URL as `https://YOUR-API.onrender.com` and check:

```powershell
Invoke-RestMethod https://YOUR-API.onrender.com/api/v1/health
```

Expected result: `status` is `ok` and `environment` is `production`.

## 3. Deploy the React SPA on Vercel

Import the same repository in Vercel and use these settings:

| Setting | Value |
| --- | --- |
| Framework preset | Vite |
| Root directory | `frontend` |
| Install command | `pnpm install --frozen-lockfile` |
| Build command | `pnpm build` |
| Output directory | `dist` |
| Node version | select a version supported by the locked Vite release (Node 20 LTS or newer) |

Set the Vercel Production environment variable before deploying:

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | `https://YOUR-API.onrender.com/api/v1` |

`VITE_API_BASE_URL` is intentionally public: Vite substitutes it into the browser bundle. Never put
a secret in a `VITE_*` variable. The committed `frontend/vercel.json` rewrites deep links such as
`/dashboard` to `index.html`, so React Router can handle them.

When Vercel gives the final production URL, update Render `CORS_ORIGINS` to that exact origin. For a
custom domain, include both the Vercel deployment hostname and custom origin during the transition,
then redeploy Render:

```text
["https://your-project.vercel.app","https://app.example.com"]
```

Do not use `*`: the API deliberately rejects wildcard origins and authenticated browser requests
need explicit origins.

## 4. Public verification sequence

1. Open the production Vercel URL and directly load `/login` and `/dashboard`; neither should be a
   Vercel 404. `/dashboard` should redirect to login while unauthenticated.
2. Register a new disposable verification account, then sign out and sign back in.
3. Create a farm and crop, then ensure the farm list remains scoped to that account.
4. Load farm weather and confirm a provider response is shown. This exercises API → Redis →
   OpenWeather and database persistence.
5. Submit a crop-health report. Run an AI/RAG request only after trusted content has been ingested
   and its calibrated safeguards are configured; do not treat an empty or unreviewed corpus as a
   successful AI verification.
6. In Neon SQL Editor, verify migration state and extensions:

   ```sql
   SELECT version_num FROM alembic_version;
   SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'vector');
   ```

If any step fails, keep the failure evidence and correct configuration before declaring the system
publicly deployed.
