"""Construction of the configured weather provider."""

from redis import Redis

from app.core.config import Settings
from app.weather.cache import WeatherCache
from app.weather.providers import ExternalWeatherProvider, MockWeatherProvider, WeatherProvider


def build_provider(settings: Settings) -> WeatherProvider:
    if settings.weather_provider == "external":
        return ExternalWeatherProvider(settings)
    return MockWeatherProvider()


def build_cache(settings: Settings) -> WeatherCache:
    return WeatherCache(
        Redis.from_url(settings.redis_url, decode_responses=True),
        settings.weather_cache_ttl_seconds,
    )
