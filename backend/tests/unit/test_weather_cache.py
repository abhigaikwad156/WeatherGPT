import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from redis.exceptions import ConnectionError as RedisConnectionError

from app.weather.cache import (
    FallbackWeatherCache,
    UpstashWeatherCache,
    WeatherCache,
)
from app.weather.providers import WeatherProviderError
from app.weather.service import WeatherService
from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather

REQUEST_PARAMETERS = {
    "provider": "openweather",
    "units": "metric",
    "current_endpoint": "/data/2.5/weather",
    "forecast_endpoint": "/data/2.5/forecast",
}


class FakeRedis:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.unavailable = unavailable

    def get(self, key: str) -> str | None:
        if self.unavailable:
            raise RedisConnectionError("Redis unavailable")
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.unavailable:
            raise RedisConnectionError("Redis unavailable")
        self.values[key] = value
        self.ttls[key] = ttl


class FakeAsyncUpstash:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float]] = {}
        self.now = 0.0
        self.unavailable = False

    def client_factory(self, *_args, **_kwargs):
        store = self

        class Client:
            async def get(self, key: str) -> str | None:
                if store.unavailable:
                    raise ConnectionError("Upstash unavailable")
                item = store.values.get(key)
                if item is None:
                    return None
                value, expires_at = item
                if store.now >= expires_at:
                    del store.values[key]
                    return None
                return value

            async def set(self, key: str, value: str, *, ex: int) -> None:
                if store.unavailable:
                    raise ConnectionError("Upstash unavailable")
                store.values[key] = (value, store.now + ex)

            async def close(self) -> None:
                return None

        return Client()


def _weather(farm_id=None) -> NormalizedWeather:
    now = datetime.now(UTC)
    return NormalizedWeather(
        farm_id=farm_id or uuid4(),
        provider="openweather",
        fetched_at=now,
        current=HourlyWeather(now, 27, 68, 0, 12, "clear", 1013),
        hourly=(),
        daily=(DailyWeather(now, 21, 30, 1, None, "cloudy"),),
        severe=(SevereWeather("Storm", "Heavy rain", "high", now),),
    )


def _upstash(store: FakeAsyncUpstash, ttl_seconds: int = 300) -> UpstashWeatherCache:
    return UpstashWeatherCache(
        "https://example.upstash.io",
        "test-token",
        ttl_seconds,
        redis_factory=store.client_factory,
    )


def test_weather_cache_round_trips_normalized_data_without_user_id() -> None:
    farm_id = uuid4()
    weather = _weather(farm_id)
    redis = FakeRedis()
    cache = WeatherCache(redis, 300)

    cache.set(weather, 18.52, 73.85, REQUEST_PARAMETERS)
    result = cache.get(farm_id, 18.52, 73.85, REQUEST_PARAMETERS)

    assert result == weather
    assert cache.get_stale(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) == weather
    assert sorted(redis.ttls.values()) == [300, 600]
    assert str(farm_id) not in next(iter(redis.values.values()))
    assert all(":v3:" in key for key in redis.values)


def test_upstash_weather_cache_hit_miss_and_ttl_expiry() -> None:
    store = FakeAsyncUpstash()
    cache = _upstash(store, ttl_seconds=300)
    farm_id = uuid4()
    weather = _weather(farm_id)

    assert cache.get(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) is None

    cache.set(weather, 18.52, 73.85, REQUEST_PARAMETERS)

    assert cache.get(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) == weather
    assert cache.get(uuid4(), 18.53, 73.85, REQUEST_PARAMETERS) is None
    assert (
        cache.get(
            farm_id,
            18.52,
            73.85,
            {**REQUEST_PARAMETERS, "units": "imperial"},
        )
        is None
    )
    assert all(str(farm_id) not in value for value, _ in store.values.values())

    store.now = 301
    assert cache.get(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) is None
    assert cache.get_stale(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) == weather
    store.now = 601
    assert cache.get_stale(farm_id, 18.52, 73.85, REQUEST_PARAMETERS) is None


def test_upstash_failure_falls_back_to_existing_redis_cache() -> None:
    store = FakeAsyncUpstash()
    store.unavailable = True
    weather = _weather()
    local_cache = WeatherCache(FakeRedis(), 300)
    local_cache.set(weather, 18.52, 73.85, REQUEST_PARAMETERS)
    cache = FallbackWeatherCache(_upstash(store), local_cache)

    assert cache.get(weather.farm_id, 18.52, 73.85, REQUEST_PARAMETERS) == weather
    cache.set(weather, 18.52, 73.85, REQUEST_PARAMETERS)
    assert local_cache.get(weather.farm_id, 18.52, 73.85, REQUEST_PARAMETERS) == weather


def test_weather_service_continues_when_upstash_and_redis_are_unavailable(monkeypatch) -> None:
    farm_id = uuid4()
    weather = _weather(farm_id)
    store = FakeAsyncUpstash()
    store.unavailable = True
    cache = FallbackWeatherCache(
        _upstash(store),
        WeatherCache(FakeRedis(unavailable=True), 300),
    )

    class Provider:
        def fetch(self, *_args):
            return weather

    service = WeatherService(object(), Provider(), cache)
    service._persist = lambda *_args: None
    farm = SimpleNamespace(
        id=farm_id,
        owner_id=uuid4(),
        latitude=18.52,
        longitude=73.85,
    )
    monkeypatch.setattr("app.weather.service.generate_weather_alerts", lambda *_args: None)

    assert service.get_weather(farm) == weather


def test_weather_service_uses_stale_cache_when_provider_fails(monkeypatch) -> None:
    farm_id = uuid4()
    stale_weather = _weather(farm_id)

    class FailingProvider:
        def fetch(self, *_args):
            raise WeatherProviderError("OpenWeather request failed")

    provider = FailingProvider()
    cache = WeatherCache(FakeRedis(), 300)
    request_parameters = WeatherService(object(), provider)._request_parameters()
    cache.set(stale_weather, 18.52, 73.85, request_parameters)

    monkeypatch.setattr("app.weather.service.generate_weather_alerts", lambda *_args: None)
    service = WeatherService(object(), provider, cache)
    farm = SimpleNamespace(
        id=farm_id,
        owner_id=uuid4(),
        latitude=18.52,
        longitude=73.85,
    )

    assert service.get_weather(farm, refresh=True) == stale_weather


def test_weather_service_deduplicates_concurrent_provider_requests(monkeypatch) -> None:
    farm_id = uuid4()
    weather = _weather(farm_id)

    class SlowProvider:
        calls = 0
        started = Event()
        release = Event()

        def fetch(self, *_args):
            self.calls += 1
            self.started.set()
            assert self.release.wait(timeout=2)
            return weather

    provider = SlowProvider()
    service = WeatherService(object(), provider)
    service._persist = lambda *_args: None
    farm = SimpleNamespace(
        id=farm_id,
        owner_id=uuid4(),
        latitude=18.52,
        longitude=73.85,
    )
    monkeypatch.setattr("app.weather.service.generate_weather_alerts", lambda *_args: None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.get_weather, farm, refresh=True)
        assert provider.started.wait(timeout=1)
        second = executor.submit(service.get_weather, farm, refresh=True)
        time.sleep(0.05)
        provider.release.set()

        assert first.result(timeout=2) == weather
        assert second.result(timeout=2) == weather

    assert provider.calls == 1
