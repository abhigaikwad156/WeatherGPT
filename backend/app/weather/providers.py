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
