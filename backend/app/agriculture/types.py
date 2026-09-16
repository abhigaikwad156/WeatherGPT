"""Provider-neutral inputs and structured outputs for agricultural decisions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DecisionType(StrEnum):
    IRRIGATION = "irrigation"
    SPRAYING = "spraying"
    SOWING_WINDOW = "sowing_window"
    EXTREME_WEATHER = "extreme_weather"
    CROP_WEATHER_COMPATIBILITY = "crop_weather_compatibility"


class DecisionValue(StrEnum):
    APPLY = "APPLY"
    WAIT = "WAIT"
    SUITABLE = "SUITABLE"
    NOT_SUITABLE = "NOT_SUITABLE"
    HIGH_RISK = "HIGH_RISK"
    LOW_RISK = "LOW_RISK"
    NEEDS_INPUT = "NEEDS_INPUT"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class WeatherSnapshot:
    """A weather observation or forecast interval supplied by a trusted source."""

    timestamp: datetime
    rainfall_mm: float | None = None
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    wind_speed_kph: float | None = None
    condition: str | None = None
    severe_weather: bool = False


@dataclass(frozen=True)
class AgriculturalInputs:
    crop: str | None = None
    growth_stage: str | None = None
    soil_type: str | None = None
    irrigation_type: str | None = None
    region: str | None = None
    recent_rainfall_mm: float | None = None
    forecast_rainfall_mm: float | None = None
    forecast_horizon_days: int | None = 3
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    wind_speed_kph: float | None = None
    soil_moisture_percent: float | None = None
    soil_moisture_measurement_basis: str | None = None
    soil_moisture_sensor_depth_cm: float | None = None
    historical_weather: tuple[WeatherSnapshot, ...] = ()
    forecast_weather: tuple[WeatherSnapshot, ...] = ()


@dataclass(frozen=True)
class Decision:
    decision_type: DecisionType
    decision: DecisionValue
    risk_level: RiskLevel
    confidence: float
    reasons: tuple[str, ...] = ()
    deterministic: bool = True
    ml_prediction: dict[str, Any] | None = None
    llm_explanation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
