"""CSV dataset loading with an explicit, leakage-safe schema."""

import csv
from dataclasses import dataclass
from pathlib import Path

FEATURE_COLUMNS = (
    "crop",
    "growth_stage",
    "soil_type",
    "irrigation_type",
    "recent_rainfall_mm",
    "forecast_rainfall_mm",
    "temperature_celsius",
    "humidity_percent",
    "wind_speed_kph",
    "soil_moisture_percent",
)
REQUIRED_COLUMNS = ("timestamp", "risk_label", *FEATURE_COLUMNS)


@dataclass(frozen=True)
class RiskRecord:
    timestamp: str
    values: dict[str, str]
    label: int


def load_csv(path: Path) -> list[RiskRecord]:
    if not path.exists():
        raise FileNotFoundError(f"ML dataset not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"dataset is missing required columns: {sorted(missing)}")
        records = []
        for row_number, row in enumerate(reader, start=2):
            try:
                label = int(row["risk_label"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid risk_label on row {row_number}") from error
            if label not in (0, 1):
                raise ValueError(f"risk_label must be 0 or 1 on row {row_number}")
            records.append(
                RiskRecord(
                    row["timestamp"],
                    {column: row[column] for column in FEATURE_COLUMNS},
                    label,
                )
            )
    if not records:
        raise ValueError("dataset contains no records")
    return records
