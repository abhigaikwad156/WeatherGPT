"""Deterministic irrigation recommendations."""

from app.agriculture.rules import missing_decision
from app.agriculture.thresholds import AgriculturalThresholds
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
    sufficient = thresholds.irrigation_soil_moisture_sufficient_percent
    rainfall = thresholds.irrigation_rainfall_lookahead_mm
    if inputs.soil_moisture_percent is None and inputs.forecast_rainfall_mm is None:
        return missing_decision(
            DecisionType.IRRIGATION, "Soil moisture or forecast rainfall is required"
        )
    if sufficient is None and rainfall is None:
        return missing_decision(DecisionType.IRRIGATION, "Irrigation thresholds are not configured")
    reasons: list[str] = []
    if sufficient is not None and inputs.soil_moisture_percent is not None:
        if inputs.soil_moisture_percent >= sufficient:
            reasons.append("Available soil moisture meets the configured sufficiency threshold")
            return Decision(
                DecisionType.IRRIGATION, DecisionValue.WAIT, RiskLevel.LOW, 0.9, tuple(reasons)
            )
    if rainfall is not None and (inputs.forecast_rainfall_mm or 0) >= rainfall:
        reasons.append("Forecast rainfall meets the configured irrigation lookahead threshold")
        return Decision(
            DecisionType.IRRIGATION, DecisionValue.WAIT, RiskLevel.LOW, 0.85, tuple(reasons)
        )
    reasons.append("Configured soil-moisture and rainfall signals do not indicate sufficient water")
    return Decision(
        DecisionType.IRRIGATION, DecisionValue.APPLY, RiskLevel.MEDIUM, 0.75, tuple(reasons)
    )
