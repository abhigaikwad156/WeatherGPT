"""Deterministic sowing-window recommendations."""

from app.agriculture.rules import missing_decision
from app.agriculture.thresholds import AgriculturalThresholds
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def recommend_sowing(inputs: AgriculturalInputs, thresholds: AgriculturalThresholds) -> Decision:
    values = (
        thresholds.sowing_min_temperature_celsius,
        thresholds.sowing_max_temperature_celsius,
        thresholds.sowing_rainfall_min_mm,
        thresholds.sowing_rainfall_max_mm,
    )
    if inputs.temperature_celsius is None or any(value is None for value in values):
        return missing_decision(
            DecisionType.SOWING_WINDOW, "Temperature and complete sowing thresholds are required"
        )
    rainfall = inputs.forecast_rainfall_mm
    if rainfall is None:
        return missing_decision(DecisionType.SOWING_WINDOW, "Forecast rainfall is required")
    if (
        not thresholds.sowing_min_temperature_celsius
        <= inputs.temperature_celsius
        <= thresholds.sowing_max_temperature_celsius
    ):
        return Decision(
            DecisionType.SOWING_WINDOW,
            DecisionValue.NOT_SUITABLE,
            RiskLevel.MEDIUM,
            0.85,
            ("Temperature is outside the configured sowing range",),
        )
    if not thresholds.sowing_rainfall_min_mm <= rainfall <= thresholds.sowing_rainfall_max_mm:
        return Decision(
            DecisionType.SOWING_WINDOW,
            DecisionValue.NOT_SUITABLE,
            RiskLevel.MEDIUM,
            0.8,
            ("Forecast rainfall is outside the configured sowing range",),
        )
    return Decision(
        DecisionType.SOWING_WINDOW,
        DecisionValue.SUITABLE,
        RiskLevel.LOW,
        0.8,
        ("Temperature and forecast rainfall are within configured sowing ranges",),
    )
