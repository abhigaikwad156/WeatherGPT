# Agricultural Weather-Related Crop Risk ML

## Dataset inspection

The repository currently contains no training dataset, labels, trained model, or ML
dependencies. The only related data is the configurable agricultural-threshold JSON.
Consequently, this implementation does not report fabricated performance metrics.
Training fails clearly until a labeled CSV is supplied.

The expected schema is shown in
[`ml/data/example_schema.csv`](../ml/data/example_schema.csv).

## Prediction target

The first target is binary weather-related crop risk for a defined prediction horizon:

- `risk_label=1`: a trusted, reviewed adverse crop-weather outcome occurred in the
  prediction horizon.
- `risk_label=0`: the reviewed horizon did not contain that adverse outcome.

The horizon and adverse-outcome definition must be documented by the dataset owner.
The model is not a weather forecaster and does not generate weather predictions.

## Features

Features are limited to information available at prediction time:

- crop
- growth stage
- soil type
- irrigation type
- recent rainfall
- forecast rainfall
- temperature
- humidity
- wind speed
- soil moisture

Historical weather may be converted into lagged summaries in a future version, provided
the summaries use only timestamps before the prediction time.

## Label generation and leakage

Labels must come from trusted observations, reviewed agronomic event records, or another
approved outcome source. Do not infer labels from the model's own recommendations.

Potential leakage includes:

- weather observations recorded after the prediction horizon
- final severe-weather alerts generated after the event
- crop damage or harvest outcomes that occur after prediction time
- recommendation status or decision output derived from the label
- imputation values calculated using future rows

The preprocessing configuration is fit on training rows only and saved with the model.
Evaluation should use chronological splits when timestamps are available.

## Baseline and evaluation

The baseline is an interpretable logistic regression implemented in
[`ml/training/logistic.py`](../ml/training/logistic.py). Categorical features are
one-hot encoded, numeric missing values use training-set means, and L2 regularization
limits coefficient growth.

Reported metrics are:

- precision
- recall
- F1
- confusion matrix
- signed feature coefficients as feature importance

No XGBoost or LightGBM is included. A more complex model should only be considered after
a real dataset, chronological validation, class balance analysis, and baseline comparison
justify it.

## Model versioning and inference

The model and preprocessing configuration are separate JSON artifacts. Inference returns
structured `CropRiskPrediction` data containing risk, probability, model version, and
feature coefficients.

The prediction is an input to the agricultural decision engine; it is not a replacement
for deterministic decisions. `llm_override_allowed` is always `false`. An LLM may explain
the structured prediction but cannot modify it.

## Current status

The implementation is ready for a trusted labeled dataset, but no performance numbers are
claimed until training is run on that dataset.
