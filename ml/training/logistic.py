"""Interpretable logistic-regression baseline implemented without hidden dependencies."""

import json
import math
from dataclasses import dataclass
from pathlib import Path


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


@dataclass
class LogisticRiskModel:
    coefficients: list[float]
    intercept: float
    version: str = "logistic-baseline-1.0.0"

    def probability(self, features: list[float]) -> float:
        if len(features) != len(self.coefficients):
            raise ValueError("feature vector does not match model")
        return _sigmoid(
            self.intercept
            + sum(
                coefficient * value
                for coefficient, value in zip(self.coefficients, features, strict=True)
            )
        )

    def predict(self, features: list[float], threshold: float = 0.5) -> int:
        return int(self.probability(features) >= threshold)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_type": "logistic_regression",
            "version": self.version,
            "coefficients": self.coefficients,
            "intercept": self.intercept,
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LogisticRiskModel":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            list(data["coefficients"]),
            float(data["intercept"]),
            str(data["version"]),
        )


def train_logistic(
    features: list[list[float]],
    labels: list[int],
    *,
    epochs: int = 1000,
    learning_rate: float = 0.05,
    l2: float = 0.01,
) -> LogisticRiskModel:
    if not features or len(features) != len(labels):
        raise ValueError("features and labels must be non-empty and have equal length")
    width = len(features[0])
    if any(len(row) != width for row in features):
        raise ValueError("all feature rows must have equal width")
    coefficients = [0.0] * width
    intercept = 0.0
    count = float(len(features))
    for _ in range(epochs):
        gradient = [0.0] * width
        intercept_gradient = 0.0
        for row, label in zip(features, labels, strict=True):
            error = (
                _sigmoid(
                    intercept
                    + sum(weight * value for weight, value in zip(coefficients, row, strict=True))
                )
                - label
            )
            intercept_gradient += error
            for index, value in enumerate(row):
                gradient[index] += error * value
        intercept -= learning_rate * intercept_gradient / count
        for index in range(width):
            coefficients[index] -= learning_rate * (
                gradient[index] / count + l2 * coefficients[index]
            )
    return LogisticRiskModel(coefficients, intercept)
