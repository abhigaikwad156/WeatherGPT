"""Load versioned model artifacts for serving."""

import json
from pathlib import Path

from ml.inference.risk import CropRiskPredictor
from ml.preprocessing.features import FeaturePreprocessor
from ml.training.logistic import LogisticRiskModel


def load_predictor(directory: Path) -> CropRiskPredictor:
    model = LogisticRiskModel.load(directory / "model.json")
    preprocessing = FeaturePreprocessor.from_dict(
        json.loads((directory / "preprocessing.json").read_text(encoding="utf-8"))
    )
    return CropRiskPredictor(model, preprocessing)
