"""Weather provider interface and adapters."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import httpx

from app.core.config import Settings
from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather


class WeatherProviderError(RuntimeError):
    """Raised when a weather provider cannot return a valid response."""


class WeatherProvider(Protocol):
    def fetch(self, farm_id: UUID, latitude: float, longitude: float) -> NormalizedWeather:
        """Fetch and normalize weather data for a farm location."""


def _number(value: object) -> float | None:
    return float(value) if value is not None else None


class ExternalWeatherProvider:
    """Adapter for a configured JSON weather API.

    The provider expects a normalized-compatible payload. This deliberately
    avoids claiming compatibility with an unverified vendor schema.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.weather_api_url or not settings.weather_api_key:
            raise WeatherProviderError(
                "WEATHER_API_URL and WEATHER_API_KEY are required for the external provider"
            )
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.weather_api_timeout_seconds)

    def fetch(self, farm_id: UUID, latitude: float, longitude: float) -> NormalizedWeather:
        last_error: Exception | None = None
        for attempt in range(self.settings.weather_api_retries + 1):
            try:
                response = self.client.get(
                    self.settings.weather_api_url,
                    params={"latitude": latitude, "longitude": longitude},
                    headers={"Authorization": f"Bearer {self.settings.weather_api_key}"},
                )
                response.raise_for_status()
                return self._normalize(farm_id, response.json())
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                last_error = error
                if attempt < self.settings.weather_api_retries:
                    continue
        raise WeatherProviderError("External weather provider request failed") from last_error

    def _normalize(self, farm_id: UUID, payload: Mapping[str, object]) -> NormalizedWeather:
        try:
            current_payload = payload.get("current")
            hourly_payload = payload.get("hourly", [])
            daily_payload = payload.get("daily", [])
            severe_payload = payload.get("severe", [])
            current = self._hourly_item(current_payload) if current_payload else None
            return NormalizedWeather(
                farm_id=farm_id,
                provider="external",
                fetched_at=datetime.now(UTC),
                current=current,
                hourly=tuple(self._hourly_item(item) for item in hourly_payload),
                daily=tuple(self._daily_item(item) for item in daily_payload),
                severe=tuple(self._severe_item(item) for item in severe_payload),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WeatherProviderError("External weather response has an invalid schema") from error

    @staticmethod
    def _hourly_item(item: object) -> HourlyWeather:
        data = item if isinstance(item, Mapping) else {}
        return HourlyWeather(
            observed_at=datetime.fromisoformat(str(data["observed_at"])),
            temperature_celsius=_number(data.get("temperature_celsius")),
            humidity_percent=_number(data.get("humidity_percent")),
            rainfall_mm=_number(data.get("rainfall_mm")),
            wind_speed_kph=_number(data.get("wind_speed_kph")),
            condition=str(data["condition"]) if data.get("condition") is not None else None,
        )

    @staticmethod
    def _daily_item(item: object) -> DailyWeather:
        data = item if isinstance(item, Mapping) else {}
        return DailyWeather(
            forecast_for=datetime.fromisoformat(str(data["forecast_for"])),
            temperature_min_celsius=_number(data.get("temperature_min_celsius")),
            temperature_max_celsius=_number(data.get("temperature_max_celsius")),
            precipitation_mm=_number(data.get("precipitation_mm")),
            rain_probability_percent=_number(data.get("rain_probability_percent")),
            condition=str(data["condition"]) if data.get("condition") is not None else None,
        )

    @staticmethod
    def _severe_item(item: object) -> SevereWeather:
        data = item if isinstance(item, Mapping) else {}
        return SevereWeather(
            title=str(data["title"]),
            description=str(data["description"]),
            severity=str(data["severity"]),
            starts_at=datetime.fromisoformat(str(data["starts_at"])),
            ends_at=datetime.fromisoformat(str(data["ends_at"])) if data.get("ends_at") else None,
        )


class OpenMeteoWeatherProvider:
    """Adapter for the free Open-Meteo forecast API."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.weather_api_url:
            raise WeatherProviderError("WEATHER_API_URL is required for the Open-Meteo provider")
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.weather_api_timeout_seconds)

    def fetch(self, farm_id: UUID, latitude: float, longitude: float) -> NormalizedWeather:
        last_error: Exception | None = None
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "UTC",
            "current": (
                "temperature_2m,relative_humidity_2m,precipitation,"
                "wind_speed_10m,weather_code"
            ),
            "hourly": (
                "temperature_2m,relative_humidity_2m,precipitation,"
                "wind_speed_10m,weather_code"
            ),
            "forecast_days": 7,
            "daily": (
                "temperature_2m_min,temperature_2m_max,precipitation_sum,"
                "precipitation_probability_max,weather_code"
            ),
        }
        for attempt in range(self.settings.weather_api_retries + 1):
            try:
                response = self.client.get(
                    self.settings.weather_api_url,
                    params=params,
                )
                response.raise_for_status()
                return self._normalize(farm_id, response.json())
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                last_error = error
                if attempt < self.settings.weather_api_retries:
                    continue
        raise WeatherProviderError("Open-Meteo weather request failed") from last_error

    def _normalize(self, farm_id: UUID, payload: Mapping[str, object]) -> NormalizedWeather:
        try:
            current_payload = payload["current"]
            hourly_payload = payload["hourly"]
            daily_payload = payload["daily"]
            current = self._current_item(current_payload)
            hourly = self._series(hourly_payload)
            daily = self._daily_series(daily_payload)
            return NormalizedWeather(
                farm_id=farm_id,
                provider="open-meteo",
                fetched_at=datetime.now(UTC),
                current=current,
                hourly=hourly,
                daily=daily,
                severe=(),
            )
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise WeatherProviderError("Open-Meteo response has an invalid schema") from error

    @classmethod
    def _current_item(cls, payload: object) -> HourlyWeather:
        data = payload if isinstance(payload, Mapping) else {}
        return HourlyWeather(
            observed_at=cls._timestamp(data["time"]),
            temperature_celsius=_number(data.get("temperature_2m")),
            humidity_percent=_number(data.get("relative_humidity_2m")),
            rainfall_mm=_number(data.get("precipitation")),
            wind_speed_kph=_number(data.get("wind_speed_10m")),
            condition=cls._condition(data.get("weather_code")),
        )

    @classmethod
    def _series(cls, payload: object) -> tuple[HourlyWeather, ...]:
        data = payload if isinstance(payload, Mapping) else {}
        times = cls._list(data["time"])
        temperatures = cls._list(data.get("temperature_2m"))
        humidity = cls._list(data.get("relative_humidity_2m"))
        rainfall = cls._list(data.get("precipitation"))
        wind = cls._list(data.get("wind_speed_10m"))
        codes = cls._list(data.get("weather_code"))
        return tuple(
            HourlyWeather(
                observed_at=cls._timestamp(time),
                temperature_celsius=_number(cls._at(temperatures, index)),
                humidity_percent=_number(cls._at(humidity, index)),
                rainfall_mm=_number(cls._at(rainfall, index)),
                wind_speed_kph=_number(cls._at(wind, index)),
                condition=cls._condition(cls._at(codes, index)),
            )
            for index, time in enumerate(times)
        )

    @classmethod
    def _daily_series(cls, payload: object) -> tuple[DailyWeather, ...]:
        data = payload if isinstance(payload, Mapping) else {}
        dates = cls._list(data["time"])
        minimum = cls._list(data.get("temperature_2m_min"))
        maximum = cls._list(data.get("temperature_2m_max"))
        precipitation = cls._list(data.get("precipitation_sum"))
        probability = cls._list(data.get("precipitation_probability_max"))
        codes = cls._list(data.get("weather_code"))
        return tuple(
            DailyWeather(
                forecast_for=cls._timestamp(date),
                temperature_min_celsius=_number(cls._at(minimum, index)),
                temperature_max_celsius=_number(cls._at(maximum, index)),
                precipitation_mm=_number(cls._at(precipitation, index)),
                rain_probability_percent=_number(cls._at(probability, index)),
                condition=cls._condition(cls._at(codes, index)),
            )
            for index, date in enumerate(dates)
        )

    @staticmethod
    def _list(value: object) -> list[object]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _at(values: list[object], index: int) -> object | None:
        return values[index] if index < len(values) else None

    @staticmethod
    def _timestamp(value: object) -> datetime:
        text = str(value)
        if len(text) == 10:
            text = f"{text}T00:00:00"
        return datetime.fromisoformat(text).replace(tzinfo=UTC)

    @staticmethod
    def _condition(code: object) -> str | None:
        if code is None:
            return None
        weather_code = int(code)
        if weather_code == 0:
            return "clear sky"
        if weather_code in (1, 2, 3):
            return "partly cloudy"
        if weather_code in (45, 48):
            return "fog"
        if weather_code in (51, 53, 55, 56, 57):
            return "drizzle"
        if weather_code in (61, 63, 65, 66, 67, 80, 81, 82):
            return "rain"
        if weather_code in (71, 73, 75, 77, 85, 86):
            return "snow"
        if weather_code in (95, 96, 99):
            return "thunderstorm"
        return "unknown"


class MockWeatherProvider:
    """Deterministic provider for local development and tests."""

    def __init__(self, response: NormalizedWeather | None = None) -> None:
        self.response = response

    def fetch(self, farm_id: UUID, latitude: float, longitude: float) -> NormalizedWeather:
        if self.response is not None:
            return self.response
        now = datetime.now(UTC)
        current = HourlyWeather(now, 27.0, 68.0, 0.0, 12.0, "partly cloudy")
        return NormalizedWeather(
            farm_id=farm_id,
            provider="mock",
            fetched_at=now,
            current=current,
            hourly=(current,),
            daily=(DailyWeather(now, 22.0, 29.0, 1.2, 25.0, "partly cloudy"),),
            severe=(),
        )
