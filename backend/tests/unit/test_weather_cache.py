import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from app.weather.cache import WeatherCache
from app.weather.providers import WeatherProviderError
from app.weather.service import WeatherService
from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def test_weather_cache_round_trips_normalized_data() -> None:
    farm_id = uuid4()
    weather = NormalizedWeather(
        farm_id=farm_id,
        provider="mock",
        fetched_at=datetime.now(UTC),
        current=HourlyWeather(datetime.now(UTC), 27, 68, 0, 12, "clear"),
        hourly=(),
        daily=(DailyWeather(datetime.now(UTC), 21, 30, 1, 20, "cloudy"),),
        severe=(SevereWeather("Storm", "Heavy rain", "high", datetime.now(UTC)),),
    )
    cache = WeatherCache(FakeRedis(), 300)

    cache.set(weather)
    result = cache.get(farm_id)

    assert result == weather
    assert cache.get_stale(farm_id) == weather
    assert cache.redis.ttls[f"weather:{farm_id}"] == 300
    assert cache.redis.ttls[f"weather:stale:{farm_id}"] == 600


def test_weather_service_uses_stale_cache_when_provider_fails(monkeypatch) -> None:
    farm_id = uuid4()
    now = datetime.now(UTC)
    stale_weather = NormalizedWeather(
        farm_id=farm_id,
        provider="openweather",
        fetched_at=now,
        current=HourlyWeather(now, 27, 68, 0, 12, "clear"),
        hourly=(),
        daily=(),
        severe=(),
    )
    cache = WeatherCache(FakeRedis(), 300)
    cache.set(stale_weather)

    class FailingProvider:
        def fetch(self, *_args):
            raise WeatherProviderError("OpenWeather request failed")

    monkeypatch.setattr("app.weather.service.generate_weather_alerts", lambda *_args: None)
    service = WeatherService(object(), FailingProvider(), cache)
    farm = SimpleNamespace(
        id=farm_id,
        owner_id=uuid4(),
        latitude=18.52,
        longitude=73.85,
    )

    assert service.get_weather(farm, refresh=True) == stale_weather


def test_weather_service_deduplicates_concurrent_provider_requests(monkeypatch) -> None:
    farm_id = uuid4()
    now = datetime.now(UTC)
    weather = NormalizedWeather(
        farm_id=farm_id,
        provider="openweather",
        fetched_at=now,
        current=HourlyWeather(now, 27, 68, 0, 12, "clear"),
        hourly=(),
        daily=(),
        severe=(),
    )

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
