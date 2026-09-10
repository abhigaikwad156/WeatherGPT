"""Leakage-aware baseline training orchestration."""

import json
from dataclasses import dataclass
from pathlib import Path

from ml.data.dataset import RiskRecord
from ml.evaluation.metrics import EvaluationMetrics, evaluate_binary
from ml.preprocessing.features import FeaturePreprocessor
from ml.training.logistic import LogisticRiskModel, train_logistic


@dataclass(frozen=True)
class TrainingResult:
    model: LogisticRiskModel
    preprocessor: FeaturePreprocessor
    metrics: EvaluationMetrics
    feature_importance: dict[str, float]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.model.save(directory / "model.json")
        (directory / "preprocessing.json").write_text(
            json.dumps(self.preprocessor.to_dict(), indent=2), encoding="utf-8"
        )
        (directory / "metrics.json").write_text(
            json.dumps(
                {
                    **self.metrics.to_dict(),
                    "feature_importance": self.feature_importance,
                    "model_version": self.model.version,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def train_baseline(records: list[RiskRecord], *, test_fraction: float = 0.2) -> TrainingResult:
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    ordered = sorted(records, key=lambda record: record.timestamp)
    split = max(1, min(len(ordered) - 1, int(len(ordered) * (1 - test_fraction))))
    train_records, test_records = ordered[:split], ordered[split:]
    if len({record.label for record in train_records}) < 2:
        raise ValueError("training split must contain both risk labels")
    preprocessor = FeaturePreprocessor.fit(train_records)
    train_features = [preprocessor.transform_record(record) for record in train_records]
    test_features = [preprocessor.transform_record(record) for record in test_records]
    model = train_logistic(train_features, [record.label for record in train_records])
    predictions = [model.predict(row) for row in test_features]
    metrics = evaluate_binary([record.label for record in test_records], predictions)
    importance = dict(zip(preprocessor.feature_names, model.coefficients, strict=True))
    return TrainingResult(model, preprocessor, metrics, importance)
