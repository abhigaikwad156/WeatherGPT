"""Deterministic extreme-weather risk assessment."""

from app.agriculture.thresholds import AgriculturalThresholds
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def assess_extreme_weather(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> Decision:
    signals: list[str] = []
    if (
        thresholds.extreme_temperature_low_celsius is not None
        and inputs.temperature_celsius is not None
        and inputs.temperature_celsius <= thresholds.extreme_temperature_low_celsius
    ):
        signals.append("Temperature is at or below the configured low-risk threshold")
    if (
        thresholds.extreme_temperature_high_celsius is not None
        and inputs.temperature_celsius is not None
        and inputs.temperature_celsius >= thresholds.extreme_temperature_high_celsius
    ):
        signals.append("Temperature is at or above the configured high-risk threshold")
    if (
        thresholds.extreme_rainfall_mm is not None
        and inputs.forecast_rainfall_mm is not None
        and inputs.forecast_rainfall_mm >= thresholds.extreme_rainfall_mm
    ):
        signals.append("Forecast rainfall meets the configured extreme-rainfall threshold")
    if (
        thresholds.extreme_wind_speed_kph is not None
        and inputs.wind_speed_kph is not None
        and inputs.wind_speed_kph >= thresholds.extreme_wind_speed_kph
    ):
        signals.append("Wind speed meets the configured extreme-wind threshold")
    if any(snapshot.severe_weather for snapshot in inputs.forecast_weather):
        signals.append("The trusted forecast contains a severe-weather signal")
    if signals:
        return Decision(
            DecisionType.EXTREME_WEATHER,
            DecisionValue.HIGH_RISK,
            RiskLevel.HIGH,
            0.9,
            tuple(signals),
        )
    configured = any(
        value is not None
        for value in (
            thresholds.extreme_temperature_low_celsius,
            thresholds.extreme_temperature_high_celsius,
            thresholds.extreme_rainfall_mm,
            thresholds.extreme_wind_speed_kph,
        )
    )
    if not configured and not any(snapshot.severe_weather for snapshot in inputs.forecast_weather):
        return Decision(
            DecisionType.EXTREME_WEATHER,
            DecisionValue.NEEDS_INPUT,
            RiskLevel.UNKNOWN,
            0.0,
            ("No configured thresholds or severe-weather forecast signal is available",),
        )
    return Decision(
        DecisionType.EXTREME_WEATHER,
        DecisionValue.LOW_RISK,
        RiskLevel.LOW,
        0.7,
        ("No configured extreme-weather rule was triggered",),
    )
