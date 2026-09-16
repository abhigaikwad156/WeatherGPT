"""Deterministic irrigation recommendations from crop-specific profiles."""

from app.agriculture.rules import missing_decision
from app.agriculture.thresholds import AgriculturalThresholds, IrrigationProfile
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def recommend_irrigation(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> Decision:
    profile = matching_irrigation_profile(inputs, thresholds)
    if profile is None:
        return missing_decision(
            DecisionType.IRRIGATION,
            "No matching crop-specific irrigation profile is configured",
        )
    soil_moisture = profile.soil_moisture
    forecast = profile.forecast
    if (
        soil_moisture.sufficient_percent is None
        or forecast.rainfall_lookahead_mm is None
        or forecast.horizon_days is None
    ):
        return missing_decision(
            DecisionType.IRRIGATION,
            "Matching irrigation profile has unreviewed threshold values",
        )
    if inputs.soil_moisture_percent is None:
        return missing_decision(
            DecisionType.IRRIGATION,
            "Soil-moisture measurement is required for this irrigation profile",
        )
    if (
        soil_moisture.measurement_basis is not None
        and inputs.soil_moisture_measurement_basis != soil_moisture.measurement_basis
    ):
        return missing_decision(
            DecisionType.IRRIGATION,
            "Soil-moisture measurement basis does not match the irrigation profile",
        )
    if (
        soil_moisture.sensor_depth_cm is not None
        and inputs.soil_moisture_sensor_depth_cm != soil_moisture.sensor_depth_cm
    ):
        return missing_decision(
            DecisionType.IRRIGATION,
            "Soil-moisture sensor depth does not match the irrigation profile",
        )
    if inputs.forecast_rainfall_mm is None:
        return missing_decision(
            DecisionType.IRRIGATION,
            "Forecast rainfall is required for this irrigation profile",
        )
    if inputs.forecast_horizon_days != forecast.horizon_days:
        return missing_decision(
            DecisionType.IRRIGATION,
            "Forecast horizon does not match the irrigation profile",
        )
    if inputs.soil_moisture_percent >= soil_moisture.sufficient_percent:
        return Decision(
            DecisionType.IRRIGATION,
            DecisionValue.WAIT,
            RiskLevel.LOW,
            0.9,
            ("Available soil moisture meets the profile's sufficiency threshold",),
        )
    if inputs.forecast_rainfall_mm >= forecast.rainfall_lookahead_mm:
        return Decision(
            DecisionType.IRRIGATION,
            DecisionValue.WAIT,
            RiskLevel.LOW,
            0.85,
            ("Forecast rainfall meets the profile's irrigation lookahead threshold",),
        )
    return Decision(
        DecisionType.IRRIGATION,
        DecisionValue.APPLY,
        RiskLevel.MEDIUM,
        0.75,
        ("Profiled soil-moisture and rainfall signals do not indicate sufficient water",),
    )


def matching_irrigation_profile(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> IrrigationProfile | None:
    if not inputs.crop:
        return None
    matches = [
        profile
        for profile in thresholds.irrigation_profiles
        if profile.is_reviewed() and _matches(profile, inputs)
    ]
    if not matches:
        return None
    most_specific = max(profile.specificity() for profile in matches)
    candidates = [profile for profile in matches if profile.specificity() == most_specific]
    # Ambiguous profiles are unsafe: config authors must make the intended
    # profile more specific rather than depending on configuration order.
    return candidates[0] if len(candidates) == 1 else None


def _matches(profile: IrrigationProfile, inputs: AgriculturalInputs) -> bool:
    return (
        profile.crop.casefold() == inputs.crop.strip().casefold()
        and _matches_dimension(profile.growth_stage, inputs.growth_stage)
        and _matches_dimension(profile.soil_type, inputs.soil_type)
        and _matches_dimension(profile.irrigation_type, inputs.irrigation_type)
        and _matches_dimension(profile.region, inputs.region)
    )


def _matches_dimension(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        return True
    return actual is not None and expected.casefold() == actual.strip().casefold()
