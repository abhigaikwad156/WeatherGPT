"""Orchestrator for deterministic agricultural decisions."""

from app.agriculture.compatibility import assess_crop_weather_compatibility
from app.agriculture.extreme_weather import assess_extreme_weather
from app.agriculture.irrigation import recommend_irrigation
from app.agriculture.sowing import recommend_sowing
from app.agriculture.spraying import recommend_spraying
from app.agriculture.thresholds import AgriculturalThresholds, load_default_thresholds
from app.agriculture.types import AgriculturalInputs, Decision, DecisionType


class AgriculturalDecisionEngine:
    """Runs deterministic rules only; ML and LLM layers are explicit output fields."""

    def __init__(self, thresholds: AgriculturalThresholds | None = None) -> None:
        self.thresholds = thresholds or load_default_thresholds()

    def evaluate(
        self,
        inputs: AgriculturalInputs,
        ml_prediction: dict[str, object] | None = None,
    ) -> dict[DecisionType, Decision]:
        decisions = {
            DecisionType.IRRIGATION: recommend_irrigation(inputs, self.thresholds),
            DecisionType.SPRAYING: recommend_spraying(inputs, self.thresholds),
            DecisionType.SOWING_WINDOW: recommend_sowing(inputs, self.thresholds),
            DecisionType.EXTREME_WEATHER: assess_extreme_weather(inputs, self.thresholds),
            DecisionType.CROP_WEATHER_COMPATIBILITY: assess_crop_weather_compatibility(
                inputs, self.thresholds
            ),
        }
        if ml_prediction is None:
            return decisions
        return {
            decision_type: Decision(
                decision.decision_type,
                decision.decision,
                decision.risk_level,
                decision.confidence,
                decision.reasons,
                decision.deterministic,
                ml_prediction,
                decision.llm_explanation,
                decision.metadata,
            )
            for decision_type, decision in decisions.items()
        }
