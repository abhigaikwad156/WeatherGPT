from ml.data.dataset import RiskRecord
from ml.evaluation.metrics import evaluate_binary
from ml.inference.risk import CropRiskPredictor
from ml.training.pipeline import train_baseline

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import AgriculturalThresholds
from app.agriculture.types import AgriculturalInputs, DecisionType


def record(timestamp: str, risk: int, temperature: str = "24") -> RiskRecord:
    return RiskRecord(
        timestamp,
        {
            "crop": "soybean",
            "growth_stage": "vegetative",
            "soil_type": "loam",
            "irrigation_type": "drip",
            "recent_rainfall_mm": "4",
            "forecast_rainfall_mm": "12",
            "temperature_celsius": temperature,
            "humidity_percent": "60",
            "wind_speed_kph": "8",
            "soil_moisture_percent": "40",
        },
        risk,
    )


def test_metrics_include_confusion_matrix() -> None:
    metrics = evaluate_binary([0, 0, 1, 1], [0, 1, 1, 0])
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1 == 0.5
    assert metrics.confusion_matrix == ((1, 1), (1, 1))


def test_training_uses_time_order_and_produces_feature_importance() -> None:
    records = [record(f"2026-09-{day:02d}", day % 2) for day in range(1, 11)]
    result = train_baseline(records)
    assert result.model.version == "logistic-baseline-1.0.0"
    assert result.feature_importance
    assert len(result.metrics.confusion_matrix) == 2


def test_prediction_is_structured_and_attached_without_llm_override() -> None:
    records = [record(f"2026-09-{day:02d}", day % 2) for day in range(1, 11)]
    trained = train_baseline(records)
    predictor = CropRiskPredictor(trained.model, trained.preprocessor)
    prediction = predictor.predict(
        AgriculturalInputs(
            crop="soybean",
            growth_stage="vegetative",
            soil_type="loam",
            irrigation_type="drip",
            recent_rainfall_mm=4,
            forecast_rainfall_mm=12,
            temperature_celsius=24,
            humidity_percent=60,
            wind_speed_kph=8,
            soil_moisture_percent=40,
        )
    )
    decision = AgriculturalDecisionEngine(AgriculturalThresholds()).evaluate(
        AgriculturalInputs(),
        prediction.to_dict(),
    )[DecisionType.IRRIGATION]
    assert decision.ml_prediction == prediction.to_dict()
    assert prediction.llm_override_allowed is False
