# WeatherGPT database model

The initial schema uses PostgreSQL with the PostGIS extension. All primary keys are UUIDs, all business tables have `created_at` and `updated_at` UTC timestamps, and foreign keys document ownership and cleanup rules.

## Tables

| Table | Purpose | Main relationships |
| --- | --- | --- |
| `users` | Authenticated farmer/administrator identity and language preference. | Owns farms, crop cycles, alerts, recommendations, conversations, and optionally messages. |
| `farms` | A named farm belonging to one user. | Stores latitude, longitude, and a PostGIS `geography(Point, 4326)` location; has crop cycles, weather data, alerts, recommendations, and conversations. |
| `crops` | Shared crop catalogue, such as onion. | Referenced by farmer crop cycles. |
| `farmer_crops` | A crop cycle for a farmer at a farm. | Belongs to a user, farm, and crop; may be referenced by alerts and recommendations. |
| `weather_observations` | A provider-sourced, observed weather reading at a farm and time. | Belongs to a farm. |
| `weather_forecasts` | A provider forecast for a farm, forecast time, and issue time. | Belongs to a farm. |
| `weather_alerts` | A weather risk notification for a user/farm and optionally a crop cycle. | Belongs to a user and farm; optionally references a farmer crop. |
| `recommendations` | Persisted output of a future deterministic decision engine. | Belongs to a user and farm; optionally references a farmer crop. |
| `conversations` | A farmer conversation, optionally scoped to a farm. | Belongs to a user; contains messages. |
| `messages` | An ordered message in a conversation. | Belongs to a conversation; may reference its user sender. |

## Geographic farm data

`farms.latitude` and `farms.longitude` are retained for straightforward input and display. Range constraints reject invalid coordinates. `farms.location` is the canonical spatial value, stored as WGS 84 (`SRID 4326`) PostGIS geography with a GiST index for later proximity and regional queries. Application code must keep all three values consistent when a farm is created or moved.

## Integrity and indexing

- User emails and crop names are unique.
- Weather readings/forecasts are unique for a farm, provider, and relevant provider timestamp(s), which prevents duplicate ingestion.
- Humidity and rain probability are constrained to 0–100; farm coordinates are constrained to valid world ranges.
- Crop harvest dates cannot precede planting dates.
- Dependent data is deleted with its user/farm where it has no independent value. A crop cycle referenced by an alert or recommendation is set to `NULL` when that crop cycle is deleted, preserving historical records.
- Foreign keys and time-based weather lookup columns are indexed. The `farms.location` spatial index is a PostGIS GiST index.

## Relationship diagram

```text
User 1---* Farm 1---* FarmerCrop *---1 Crop
 |          |             |
 |          |             +---* WeatherAlert
 |          +---* WeatherObservation
 |          +---* WeatherForecast
 |          +---* Recommendation
 |          +---* Conversation 1---* Message
 +---* WeatherAlert / Recommendation / Conversation
```

## Migration policy

Alembic migration `20260910_0002` enables PostGIS and creates the tables. Domain tables must only be changed through a new, reviewed migration; never use `Base.metadata.create_all()` in application startup.
