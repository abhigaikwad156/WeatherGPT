"""Normalized weather data types shared by providers and consumers."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class HourlyWeather:
    observed_at: datetime
    temperature_celsius: float | None
    humidity_percent: float | None
    rainfall_mm: float | None
    wind_speed_kph: float | None
    condition: str | None


@dataclass(frozen=True)
class DailyWeather:
    forecast_for: datetime
    temperature_min_celsius: float | None
    temperature_max_celsius: float | None
    precipitation_mm: float | None
    rain_probability_percent: float | None
    condition: str | None


@dataclass(frozen=True)
class SevereWeather:
    title: str
    description: str
    severity: str
    starts_at: datetime
    ends_at: datetime | None = None


@dataclass(frozen=True)
class NormalizedWeather:
    farm_id: UUID
    provider: str
    fetched_at: datetime
    current: HourlyWeather | None
    hourly: tuple[HourlyWeather, ...]
    daily: tuple[DailyWeather, ...]
    severe: tuple[SevereWeather, ...]
