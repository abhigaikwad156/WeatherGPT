"""Aggregated farmer dashboard response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DashboardWeather(BaseModel):
    temperature_celsius: float | None = Field(serialization_alias="temperatureCelsius")
    condition: str | None
    rainfall_mm: float | None = Field(serialization_alias="rainfallMm")
    observed_at: datetime | None = Field(serialization_alias="observedAt")

    model_config = ConfigDict(populate_by_name=True)


class DashboardForecast(BaseModel):
    forecast_for: datetime = Field(serialization_alias="forecastFor")
    temperature_min_celsius: float | None = Field(serialization_alias="temperatureMinCelsius")
    temperature_max_celsius: float | None = Field(serialization_alias="temperatureMaxCelsius")
    precipitation_mm: float | None = Field(serialization_alias="precipitationMm")
    rain_probability_percent: float | None = Field(serialization_alias="rainProbabilityPercent")

    model_config = ConfigDict(populate_by_name=True)


class DashboardAlert(BaseModel):
    id: UUID
    title: str
    body: str
    severity: str
    starts_at: datetime = Field(serialization_alias="startsAt")

    model_config = ConfigDict(populate_by_name=True)


class DashboardCrop(BaseModel):
    name: str
    growth_stage: str | None = Field(serialization_alias="growthStage")

    model_config = ConfigDict(populate_by_name=True)


class DashboardRecommendation(BaseModel):
    id: UUID
    recommendation_type: str = Field(serialization_alias="recommendationType")
    status: str
    summary: str
    decision_version: str = Field(serialization_alias="decisionVersion")

    model_config = ConfigDict(populate_by_name=True)


class DashboardResponse(BaseModel):
    current_weather: DashboardWeather | None = Field(serialization_alias="currentWeather")
    forecast: list[DashboardForecast]
    active_alerts: list[DashboardAlert] = Field(serialization_alias="activeAlerts")
    current_crop: DashboardCrop | None = Field(serialization_alias="currentCrop")
    recommended_actions: list[DashboardRecommendation] = Field(
        serialization_alias="recommendedActions"
    )
    upcoming_risks: list[DashboardAlert] = Field(serialization_alias="upcomingRisks")

    model_config = ConfigDict(populate_by_name=True)
