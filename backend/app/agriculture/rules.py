"""Small helpers shared by deterministic agricultural rules."""

from app.agriculture.thresholds import AgriculturalThresholds, CropProfile
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)


def missing_decision(decision_type: DecisionType, reason: str) -> Decision:
    return Decision(
        decision_type,
        DecisionValue.NEEDS_INPUT,
        RiskLevel.UNKNOWN,
        0.0,
        (reason,),
    )


def crop_profile(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> CropProfile | None:
    if not inputs.crop or not thresholds.crop_profiles:
        return None
    return thresholds.crop_profiles.get(inputs.crop.strip().lower())
