"""Weather service API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HourlyWeatherResponse(BaseModel):
    observed_at: datetime
    temperature_celsius: float | None
    humidity_percent: float | None
    rainfall_mm: float | None
    wind_speed_kph: float | None
    condition: str | None


class DailyWeatherResponse(BaseModel):
    forecast_for: datetime
    temperature_min_celsius: float | None
    temperature_max_celsius: float | None
    precipitation_mm: float | None
    rain_probability_percent: float | None
    condition: str | None


class SevereWeatherResponse(BaseModel):
    title: str
    description: str
    severity: str
    starts_at: datetime
    ends_at: datetime | None


class WeatherResponse(BaseModel):
    farm_id: UUID
    provider: str
    fetched_at: datetime
    current: HourlyWeatherResponse | None
    hourly: list[HourlyWeatherResponse]
    daily: list[DailyWeatherResponse]
    severe: list[SevereWeatherResponse]
