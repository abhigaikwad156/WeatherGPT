"""Deterministic spraying-window recommendations."""

from app.agriculture.rules import crop_profile, missing_decision
from app.agriculture.thresholds import AgriculturalThresholds
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def recommend_spraying(inputs: AgriculturalInputs, thresholds: AgriculturalThresholds) -> Decision:
    profile = crop_profile(inputs, thresholds)
    max_wind = thresholds.spray_max_wind_speed_kph or (
        profile.maximum_wind_speed_kph_for_spraying if profile else None
    )
    if inputs.wind_speed_kph is None or inputs.humidity_percent is None:
        return missing_decision(DecisionType.SPRAYING, "Wind speed and humidity are required")
    if (
        max_wind is None
        or thresholds.spray_min_humidity_percent is None
        or thresholds.spray_max_humidity_percent is None
    ):
        return missing_decision(DecisionType.SPRAYING, "Spraying thresholds are not configured")
    if inputs.wind_speed_kph > max_wind:
        return Decision(
            DecisionType.SPRAYING,
            DecisionValue.WAIT,
            RiskLevel.HIGH,
            0.9,
            ("Wind exceeds the configured spraying limit",),
        )
    if (
        not thresholds.spray_min_humidity_percent
        <= inputs.humidity_percent
        <= thresholds.spray_max_humidity_percent
    ):
        return Decision(
            DecisionType.SPRAYING,
            DecisionValue.WAIT,
            RiskLevel.MEDIUM,
            0.8,
            ("Humidity is outside the configured spraying window",),
        )
    if (
        thresholds.spray_rainfall_lookahead_mm is not None
        and (inputs.forecast_rainfall_mm or 0) >= thresholds.spray_rainfall_lookahead_mm
    ):
        return Decision(
            DecisionType.SPRAYING,
            DecisionValue.WAIT,
            RiskLevel.MEDIUM,
            0.85,
            ("Forecast rainfall is within the configured wash-off window",),
        )
    return Decision(
        DecisionType.SPRAYING,
        DecisionValue.APPLY,
        RiskLevel.LOW,
        0.8,
        ("Configured wind, humidity, and rainfall conditions are suitable",),
    )
