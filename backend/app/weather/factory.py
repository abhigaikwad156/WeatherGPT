"""Construction of the configured weather provider."""

import logging

from redis import Redis

from app.core.config import Settings
from app.weather.cache import (
    FallbackWeatherCache,
    UpstashWeatherCache,
    WeatherCache,
    WeatherCacheBackend,
)
from app.weather.providers import (
    ExternalWeatherProvider,
    MockWeatherProvider,
    OpenWeatherProvider,
    WeatherProvider,
)

logger = logging.getLogger(__name__)


def build_provider(settings: Settings) -> WeatherProvider:
    if settings.weather_provider == "external":
        return ExternalWeatherProvider(settings)
    if settings.weather_provider == "openweather":
        return OpenWeatherProvider(settings)
    return MockWeatherProvider()


def build_cache(settings: Settings) -> WeatherCacheBackend:
    fallback = WeatherCache(
        Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        ),
        settings.weather_cache_ttl_seconds,
    )
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        primary = UpstashWeatherCache(
            settings.upstash_redis_rest_url,
            settings.upstash_redis_rest_token,
            settings.weather_cache_ttl_seconds,
        )
        return FallbackWeatherCache(primary, fallback)
    if settings.upstash_redis_rest_url or settings.upstash_redis_rest_token:
        logger.warning(
            "Upstash REST cache requires both UPSTASH_REDIS_REST_URL and "
            "UPSTASH_REDIS_REST_TOKEN; using REDIS_URL cache"
        )
    return fallback
