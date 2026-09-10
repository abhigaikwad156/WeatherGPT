"""Deterministic crop-weather compatibility assessment."""

from app.agriculture.rules import crop_profile, missing_decision
from app.agriculture.thresholds import AgriculturalThresholds
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def assess_crop_weather_compatibility(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> Decision:
    profile = crop_profile(inputs, thresholds)
    if profile is None or inputs.temperature_celsius is None:
        return missing_decision(
            DecisionType.CROP_WEATHER_COMPATIBILITY, "Crop profile and temperature are required"
        )
    reasons: list[str] = []
    if (
        profile.minimum_temperature_celsius is not None
        and inputs.temperature_celsius < profile.minimum_temperature_celsius
    ):
        reasons.append("Temperature is below the configured crop range")
    if (
        profile.maximum_temperature_celsius is not None
        and inputs.temperature_celsius > profile.maximum_temperature_celsius
    ):
        reasons.append("Temperature is above the configured crop range")
    if reasons:
        return Decision(
            DecisionType.CROP_WEATHER_COMPATIBILITY,
            DecisionValue.NOT_SUITABLE,
            RiskLevel.HIGH,
            0.85,
            tuple(reasons),
        )
    return Decision(
        DecisionType.CROP_WEATHER_COMPATIBILITY,
        DecisionValue.SUITABLE,
        RiskLevel.LOW,
        0.75,
        ("Temperature is within the configured crop range",),
    )
