# WeatherGPT

WeatherGPT is an agricultural weather decision-support system. The current implementation is backend infrastructure only; no weather, AI, farmer, or agricultural-recommendation features have been added.

## Local setup

1. Copy `.env.example` to `.env` and replace development values as appropriate.
2. Start the stack with `docker compose up --build`.
3. Open `http://localhost:8000/api/v1/health` or `http://localhost:8000/docs`.

The backend applies Alembic migrations before startup. Without Docker, install Python 3.12+, then from `backend` run `pip install -e .[dev]`, `alembic upgrade head`, and `uvicorn app.main:app --reload`. Run tests with `pytest` from `backend`.

See [the technical architecture and implementation plan](ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md).

## Farmer profile APIs

Authenticated requests use `Authorization: Bearer <access_token>`. The interactive OpenAPI
documentation is available at `http://localhost:8000/docs`.

- `GET/PATCH /api/v1/users/me/profile` — read or update preferred language, location, and units.
- `POST /api/v1/farms` — create a farm with coordinates, area, soil, irrigation, and optional moisture.
- `GET /api/v1/farms` — list only the authenticated farmer's farms.
- `GET/PATCH/DELETE /api/v1/farms/{farm_id}` — manage an owned farm.
- `POST/GET /api/v1/farms/{farm_id}/crops` — create or list crops associated with an owned farm.
- `GET/PATCH/DELETE /api/v1/farms/{farm_id}/crops/{crop_id}` — manage an owned crop record.

Farm and crop resources are always scoped to the authenticated user. Requests for another user's
resource return `404` rather than exposing whether the resource exists. Apply the
`20260910_0003` Alembic migration before using the new profile fields.

## Current-location names

`POST /api/v1/location/current` stores an authenticated user's explicitly submitted browser GPS
coordinates and then performs best-effort, server-side reverse geocoding through
[OpenStreetMap Nominatim](https://nominatim.org/release-docs/develop/api/Reverse/). The response
and subsequent `GET /api/v1/location/current` include a normalized `location_name` and available
city, district, state, and country fields. If Nominatim is unavailable, coordinates are still
saved and `location_name` remains `null`; the UI displays “Location saved” rather than inventing
a place name.

Set `NOMINATIM_BASE_URL`, `NOMINATIM_USER_AGENT`, and `NOMINATIM_TIMEOUT_SECONDS` in deployment
configuration. `NOMINATIM_USER_AGENT` must identify the deployment and should include a monitored
contact channel before production use. A successful result is retained with the latest exact
coordinates, so resubmitting unchanged coordinates does not make another request. The backend spaces provider
requests by at least one second per process in line with the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/). The frontend
shows © OpenStreetMap contributors attribution where the location action is available.

## Conversational weather API

`POST /api/v1/conversations/messages` accepts an authenticated request:

```json
{
  "content": "Will it rain tomorrow?",
  "language": "en",
  "farm_id": "optional-owned-farm-uuid",
  "conversation_id": "optional-existing-conversation-uuid"
}
```

The response contains a natural-language explanation and structured `message.metadata`.
Metadata includes the detected intent (`CURRENT_WEATHER`, `FORECAST`, `RAINFALL`,
`WEATHER_ALERT`, or `UNKNOWN`), farm, provider source, and verified weather records.
The API reads weather observations, forecasts, and alerts from the database through
`WeatherTool`; the explanation layer does not answer weather questions from model knowledge.
Unknown questions return guidance without fabricated weather data.

## Provider-independent weather service

The weather service uses a `WeatherProvider` contract with `MockWeatherProvider` for local
development/tests and `ExternalWeatherProvider` only when `WEATHER_PROVIDER=external` is
configured. External requests require both `WEATHER_API_URL` and `WEATHER_API_KEY`, use the
configured timeout and retry count, and must return the documented normalized JSON shape.
No vendor-specific API integration is claimed by default.

`GET /api/v1/farms/{farm_id}/weather` returns normalized current, hourly, daily, and severe
weather data for an owned farm. Responses are cached in Redis and useful current/daily data is
persisted to the weather observation and forecast tables. Redis failures do not make verified
provider data unavailable; the service falls back to the provider and database.
cd D:\WeatherGPT\frontend
>> 
>> pnpm install
>> pnpm dev

cd D:\WeatherGPT

Copy-Item .env.example .env

docker compose up --build
