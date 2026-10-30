"""Redis caching boundary for normalized weather responses."""

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from typing import Any, Protocol, TypeVar
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from upstash_redis.asyncio import Redis as AsyncUpstashRedis

from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather

logger = logging.getLogger(__name__)
T = TypeVar("T")
RequestParameters = Mapping[str, str | int | float | bool | None]


class WeatherCacheBackend(Protocol):
    def get(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None: ...

    def get_stale(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None: ...

    def set(
        self,
        weather: NormalizedWeather,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> None: ...


class WeatherCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def get(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None:
        return self._get(
            farm_id,
            self._key(latitude, longitude, request_parameters),
        )

    def get_stale(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None:
        return self._get(
            farm_id,
            self._key(latitude, longitude, request_parameters, stale=True),
        )

    def _get(self, farm_id: UUID, key: str) -> NormalizedWeather | None:
        try:
            raw = self.redis.get(key)
        except RedisError as error:
            logger.warning("Weather cache read failed (%s)", type(error).__name__)
            return None
        return _deserialize_weather(raw, farm_id)

    def set(
        self,
        weather: NormalizedWeather,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> None:
        payload = _serialize_weather(weather)
        key = self._key(latitude, longitude, request_parameters)
        try:
            self.redis.setex(key, self.ttl_seconds, payload)
            self.redis.setex(
                self._key(latitude, longitude, request_parameters, stale=True),
                self.ttl_seconds * 2,
                payload,
            )
        except RedisError as error:
            logger.warning("Weather cache write failed (%s)", type(error).__name__)

    @staticmethod
    def _key(
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
        *,
        stale: bool = False,
    ) -> str:
        fingerprint = _cache_fingerprint(latitude, longitude, request_parameters)
        prefix = "weather:stale" if stale else "weather"
        return f"{prefix}:v3:{fingerprint}"


class UpstashWeatherCache(WeatherCache):
    """Upstash REST cache using the async SDK behind the existing sync service API."""

    REQUEST_TIMEOUT_SECONDS = 1.0

    def __init__(
        self,
        url: str,
        token: str,
        ttl_seconds: int,
        redis_factory: Callable[..., Any] = AsyncUpstashRedis,
    ) -> None:
        self.url = url
        self.token = token
        self.ttl_seconds = ttl_seconds
        self.redis_factory = redis_factory

    def _run(self, operation: Callable[[], Awaitable[T]]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation())
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(operation())).result()

    async def _get_async(self, key: str) -> str | bytes | None:
        client = self.redis_factory(self.url, self.token, rest_retries=0)
        try:
            value = await asyncio.wait_for(
                client.get(key),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            return value if isinstance(value, (str, bytes)) else None
        finally:
            await client.close()

    async def _set_async(self, key: str, payload: str, ttl_seconds: int) -> None:
        client = self.redis_factory(self.url, self.token, rest_retries=0)
        try:
            await asyncio.wait_for(
                client.set(key, payload, ex=ttl_seconds),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
        finally:
            await client.close()

    def _get(self, farm_id: UUID, key: str) -> NormalizedWeather | None:
        try:
            raw = self._run(lambda: self._get_async(key))
        except Exception as error:
            logger.warning("Upstash weather cache read failed (%s)", type(error).__name__)
            return None
        return _deserialize_weather(raw, farm_id)

    def set(
        self,
        weather: NormalizedWeather,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> None:
        payload = _serialize_weather(weather)
        key = self._key(latitude, longitude, request_parameters)
        try:
            self._run(lambda: self._set_async(key, payload, self.ttl_seconds))
            self._run(
                lambda: self._set_async(
                    self._key(latitude, longitude, request_parameters, stale=True),
                    payload,
                    self.ttl_seconds * 2,
                )
            )
        except Exception as error:
            logger.warning("Upstash weather cache write failed (%s)", type(error).__name__)


class FallbackWeatherCache:
    """Use Upstash as shared cache and retain the configured Redis cache as fallback."""

    def __init__(self, primary: WeatherCacheBackend, fallback: WeatherCacheBackend) -> None:
        self.primary = primary
        self.fallback = fallback

    def get(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None:
        return self.primary.get(
            farm_id, latitude, longitude, request_parameters
        ) or self.fallback.get(farm_id, latitude, longitude, request_parameters)

    def get_stale(
        self,
        farm_id: UUID,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> NormalizedWeather | None:
        return self.primary.get_stale(
            farm_id, latitude, longitude, request_parameters
        ) or self.fallback.get_stale(farm_id, latitude, longitude, request_parameters)

    def set(
        self,
        weather: NormalizedWeather,
        latitude: float,
        longitude: float,
        request_parameters: RequestParameters,
    ) -> None:
        self.primary.set(weather, latitude, longitude, request_parameters)
        self.fallback.set(weather, latitude, longitude, request_parameters)


def _cache_fingerprint(
    latitude: float,
    longitude: float,
    request_parameters: RequestParameters,
) -> str:
    identity = json.dumps(
        {
            "schema": 3,
            "latitude": repr(latitude),
            "longitude": repr(longitude),
            "request": request_parameters,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _serialize_weather(weather: NormalizedWeather) -> str:
    payload = asdict(weather)
    payload.pop("farm_id")
    return json.dumps(payload, default=_json_default)


def _deserialize_weather(raw: str | bytes | None, farm_id: UUID) -> NormalizedWeather | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
        return NormalizedWeather(
            farm_id=farm_id,
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        logger.warning("Invalid weather cache entry ignored (%s)", type(error).__name__)
        return None


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
