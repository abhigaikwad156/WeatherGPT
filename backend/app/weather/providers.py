"""Weather provider interface and adapters."""

import logging
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol
from urllib.parse import quote, quote_plus
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


class _ApiKeyLogFilter(logging.Filter):
    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.encoded_keys = (api_key, quote(api_key, safe=""), quote_plus(api_key, safe=""))

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for key in self.encoded_keys:
            message = message.replace(key, "[REDACTED]")
        if message != record.getMessage():
            record.msg = message
            record.args = ()
        return True


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


class OpenWeatherProvider:
    """Adapter for OpenWeather current conditions and 5-day forecast APIs."""

    BASE_URL = "https://api.openweathermap.org"
    CURRENT_PATH = "/data/2.5/weather"
    FORECAST_PATH = "/data/2.5/forecast"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.openweather_api_key:
            raise WeatherProviderError(
                "OPENWEATHER_API_KEY is required for the OpenWeather provider"
            )
        for logger_name in ("httpx", "httpcore"):
            logger = logging.getLogger(logger_name)
            if not any(
                isinstance(log_filter, _ApiKeyLogFilter)
                and log_filter.api_key == settings.openweather_api_key
                for log_filter in logger.filters
            ):
                logger.addFilter(_ApiKeyLogFilter(settings.openweather_api_key))
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.weather_api_timeout_seconds)

    def fetch(self, farm_id: UUID, latitude: float, longitude: float) -> NormalizedWeather:
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.settings.openweather_api_key,
            "units": "metric",
        }
        try:
            current_payload = self._request_json(self.CURRENT_PATH, params)
            forecast_payload = self._request_json(self.FORECAST_PATH, params)
            current = self._current_item(current_payload)
            hourly, daily = self._forecast_series(forecast_payload)
            return NormalizedWeather(
                farm_id=farm_id,
                provider="openweather",
                fetched_at=datetime.now(UTC),
                current=current,
                hourly=hourly,
                daily=daily,
                severe=(),
            )
        except (KeyError, TypeError, ValueError, OverflowError, OSError) as error:
            raise WeatherProviderError("OpenWeather response has an invalid schema") from error

    def _request_json(self, path: str, params: dict[str, object]) -> Mapping[str, object]:
        last_error: Exception | None = None
        for attempt in range(self.settings.weather_api_retries + 1):
            try:
                response = self.client.get(f"{self.BASE_URL}{path}", params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ValueError("Weather response must be an object")
                return payload
            except httpx.HTTPStatusError as error:
                last_error = error
                if error.response.status_code == 429 or error.response.status_code < 500:
                    break
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
            if attempt < self.settings.weather_api_retries:
                continue
        raise WeatherProviderError("OpenWeather request failed") from last_error

    @classmethod
    def _current_item(cls, payload: Mapping[str, object]) -> HourlyWeather:
        main = cls._mapping(payload.get("main"))
        rain = cls._mapping(payload.get("rain"))
        wind = cls._mapping(payload.get("wind"))
        return HourlyWeather(
            observed_at=cls._timestamp(payload["dt"]),
            temperature_celsius=_number(main.get("temp")),
            humidity_percent=_number(main.get("humidity")),
            rainfall_mm=_number(rain.get("1h", rain.get("3h"))),
            wind_speed_kph=cls._wind_speed(wind.get("speed")),
            condition=cls._condition(payload.get("weather")),
            pressure_hpa=_number(main.get("pressure")),
        )

    @classmethod
    def _forecast_series(
        cls, payload: Mapping[str, object]
    ) -> tuple[tuple[HourlyWeather, ...], tuple[DailyWeather, ...]]:
        forecast = payload.get("list")
        if not isinstance(forecast, list):
            raise ValueError("Forecast response has no forecast list")
        city = cls._mapping(payload.get("city"))
        offset_seconds = int(_number(city.get("timezone")) or 0)
        local_timezone = timezone(timedelta(seconds=offset_seconds))
        hourly = tuple(
            cls._forecast_item(item)
            for item in sorted(forecast, key=lambda item: cls._timestamp(cls._mapping(item)["dt"]))
        )
        by_day: dict[date, list[Mapping[str, object]]] = defaultdict(list)
        for item in forecast:
            data = cls._mapping(item)
            by_day[cls._timestamp(data["dt"]).astimezone(local_timezone).date()].append(data)
        daily = tuple(
            cls._daily_item(day, items, local_timezone)
            for day, items in sorted(by_day.items())[:5]
        )
        return hourly, daily

    @classmethod
    def _forecast_item(cls, item: object) -> HourlyWeather:
        data = cls._mapping(item)
        main = cls._mapping(data.get("main"))
        rain = cls._mapping(data.get("rain"))
        wind = cls._mapping(data.get("wind"))
        return HourlyWeather(
            observed_at=cls._timestamp(data["dt"]),
            temperature_celsius=_number(main.get("temp")),
            humidity_percent=_number(main.get("humidity")),
            rainfall_mm=_number(rain.get("3h")),
            wind_speed_kph=cls._wind_speed(wind.get("speed")),
            condition=cls._condition(data.get("weather")),
            pressure_hpa=_number(main.get("pressure")),
        )

    @classmethod
    def _daily_item(
        cls,
        day: date,
        items: list[Mapping[str, object]],
        local_timezone: timezone,
    ) -> DailyWeather:
        temperatures_min: list[float] = []
        temperatures_max: list[float] = []
        rainfall: list[float] = []
        probabilities: list[float] = []
        conditions: list[str] = []
        for item in items:
            main = cls._mapping(item.get("main"))
            rain = cls._mapping(item.get("rain"))
            minimum = _number(main.get("temp_min"))
            maximum = _number(main.get("temp_max"))
            amount = _number(rain.get("3h"))
            probability = _number(item.get("pop"))
            if minimum is not None:
                temperatures_min.append(minimum)
            if maximum is not None:
                temperatures_max.append(maximum)
            if amount is not None:
                rainfall.append(amount)
            if probability is not None:
                probabilities.append(probability * 100)
            condition = cls._condition(item.get("weather"))
            if condition:
                conditions.append(condition)
        return DailyWeather(
            forecast_for=datetime.combine(day, time.min, tzinfo=local_timezone),
            temperature_min_celsius=min(temperatures_min) if temperatures_min else None,
            temperature_max_celsius=max(temperatures_max) if temperatures_max else None,
            precipitation_mm=sum(rainfall) if rainfall else None,
            rain_probability_percent=max(probabilities) if probabilities else None,
            condition=Counter(conditions).most_common(1)[0][0] if conditions else None,
        )

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _timestamp(value: object) -> datetime:
        return datetime.fromtimestamp(float(value), UTC)

    @staticmethod
    def _wind_speed(value: object) -> float | None:
        speed_meters_per_second = _number(value)
        return speed_meters_per_second * 3.6 if speed_meters_per_second is not None else None

    @staticmethod
    def _condition(value: object) -> str | None:
        weather = value[0] if isinstance(value, list) and value else None
        description = OpenWeatherProvider._mapping(weather).get("description")
        if description is None:
            return None
        return str(description)


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
