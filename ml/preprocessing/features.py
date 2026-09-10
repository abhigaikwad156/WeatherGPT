"""Serializable one-hot and numeric preprocessing."""

from dataclasses import dataclass

from ml.data.dataset import FEATURE_COLUMNS, RiskRecord

NUMERIC_COLUMNS = (
    "recent_rainfall_mm",
    "forecast_rainfall_mm",
    "temperature_celsius",
    "humidity_percent",
    "wind_speed_kph",
    "soil_moisture_percent",
)
CATEGORICAL_COLUMNS = tuple(column for column in FEATURE_COLUMNS if column not in NUMERIC_COLUMNS)


@dataclass
class FeaturePreprocessor:
    categories: dict[str, list[str]]
    means: dict[str, float]
    feature_names: list[str]

    @classmethod
    def fit(cls, records: list[RiskRecord]) -> "FeaturePreprocessor":
        categories = {
            column: sorted({record.values[column] for record in records if record.values[column]})
            for column in CATEGORICAL_COLUMNS
        }
        means = {}
        for column in NUMERIC_COLUMNS:
            values = [
                float(record.values[column]) for record in records if record.values[column].strip()
            ]
            means[column] = sum(values) / len(values) if values else 0.0
        feature_names = [
            f"{column}={category}"
            for column in CATEGORICAL_COLUMNS
            for category in categories[column]
        ] + list(NUMERIC_COLUMNS)
        return cls(categories, means, feature_names)

    def transform_record(self, record: RiskRecord) -> list[float]:
        values: list[float] = []
        for column in CATEGORICAL_COLUMNS:
            values.extend(
                1.0 if record.values[column] == category else 0.0
                for category in self.categories[column]
            )
        values.extend(self._numeric(record.values[column], column) for column in NUMERIC_COLUMNS)
        return values

    def _numeric(self, value: str, column: str) -> float:
        return float(value) if value.strip() else self.means[column]

    def to_dict(self) -> dict[str, object]:
        return {
            "categories": self.categories,
            "means": self.means,
            "feature_names": self.feature_names,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "FeaturePreprocessor":
        return cls(
            categories={key: list(value) for key, value in data["categories"].items()},
            means={key: float(value) for key, value in data["means"].items()},
            feature_names=list(data["feature_names"]),
        )
