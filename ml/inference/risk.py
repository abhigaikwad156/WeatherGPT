"""Structured crop-risk inference for the agricultural decision engine."""

from dataclasses import dataclass
from typing import Any

from app.agriculture.types import AgriculturalInputs
from ml.preprocessing.features import FeaturePreprocessor
from ml.training.logistic import LogisticRiskModel


@dataclass(frozen=True)
class CropRiskPrediction:
    risk: str
    probability: float
    model_version: str
    feature_importance: dict[str, float]
    deterministic: bool = False
    llm_override_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk,
            "probability": self.probability,
            "model_version": self.model_version,
            "feature_importance": self.feature_importance,
            "deterministic": self.deterministic,
            "llm_override_allowed": self.llm_override_allowed,
        }


class CropRiskPredictor:
    def __init__(self, model: LogisticRiskModel, preprocessor: FeaturePreprocessor):
        self.model = model
        self.preprocessor = preprocessor

    def predict(self, inputs: AgriculturalInputs) -> CropRiskPrediction:
        values = {
            "crop": inputs.crop or "",
            "growth_stage": inputs.growth_stage or "",
            "soil_type": inputs.soil_type or "",
            "irrigation_type": inputs.irrigation_type or "",
            "recent_rainfall_mm": ""
            if inputs.recent_rainfall_mm is None
            else str(inputs.recent_rainfall_mm),
            "forecast_rainfall_mm": ""
            if inputs.forecast_rainfall_mm is None
            else str(inputs.forecast_rainfall_mm),
            "temperature_celsius": ""
            if inputs.temperature_celsius is None
            else str(inputs.temperature_celsius),
            "humidity_percent": ""
            if inputs.humidity_percent is None
            else str(inputs.humidity_percent),
            "wind_speed_kph": "" if inputs.wind_speed_kph is None else str(inputs.wind_speed_kph),
            "soil_moisture_percent": ""
            if inputs.soil_moisture_percent is None
            else str(inputs.soil_moisture_percent),
        }
        from ml.data.dataset import RiskRecord

        record = RiskRecord("", values, 0)
        features = self.preprocessor.transform_record(record)
        probability = self.model.probability(features)
        return CropRiskPrediction(
            "HIGH" if probability >= 0.5 else "LOW",
            probability,
            self.model.version,
            {
                name: coefficient
                for name, coefficient in zip(
                    self.preprocessor.feature_names, self.model.coefficients, strict=True
                )
            },
        )
