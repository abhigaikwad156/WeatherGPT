"""Redis caching boundary for normalized weather responses."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather


class WeatherCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def get(self, farm_id: UUID) -> NormalizedWeather | None:
        try:
            raw = self.redis.get(f"weather:{farm_id}")
        except RedisError:
            return None
        if raw is None:
            return None
        payload = json.loads(raw)
        return NormalizedWeather(
            farm_id=UUID(payload["farm_id"]),
            provider=payload["provider"],
            fetched_at=datetime.fromisoformat(payload["fetched_at"]),
            current=HourlyWeather(**_datetime_values(payload["current"], ["observed_at"]))
            if payload["current"]
            else None,
            hourly=tuple(
                HourlyWeather(**_datetime_values(item, ["observed_at"]))
                for item in payload["hourly"]
            ),
            daily=tuple(
                DailyWeather(**_datetime_values(item, ["forecast_for"]))
                for item in payload["daily"]
            ),
            severe=tuple(
                SevereWeather(**_datetime_values(item, ["starts_at", "ends_at"]))
                for item in payload["severe"]
            ),
        )

    def set(self, weather: NormalizedWeather) -> None:
        try:
            self.redis.setex(
                f"weather:{weather.farm_id}",
                self.ttl_seconds,
                json.dumps(asdict(weather), default=_json_default),
            )
        except RedisError:
            return


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _datetime_values(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    values = dict(payload)
    for field in fields:
        if values.get(field):
            values[field] = datetime.fromisoformat(values[field])
    return values
