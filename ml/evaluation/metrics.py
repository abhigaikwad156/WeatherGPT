"""Binary classification metrics with no optimistic defaults."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationMetrics:
    precision: float
    recall: float
    f1: float
    confusion_matrix: tuple[tuple[int, int], tuple[int, int]]

    def to_dict(self) -> dict[str, object]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "confusion_matrix": self.confusion_matrix,
        }


def evaluate_binary(labels: list[int], predictions: list[int]) -> EvaluationMetrics:
    if len(labels) != len(predictions) or not labels:
        raise ValueError("labels and predictions must be non-empty and have equal length")
    tn = fp = fn = tp = 0
    for label, prediction in zip(labels, predictions, strict=True):
        if label == 1 and prediction == 1:
            tp += 1
        elif label == 0 and prediction == 1:
            fp += 1
        elif label == 1:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return EvaluationMetrics(precision, recall, f1, ((tn, fp), (fn, tp)))
