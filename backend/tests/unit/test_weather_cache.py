from datetime import UTC, datetime
from uuid import uuid4

from app.weather.cache import WeatherCache
from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.values[key] = value


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
