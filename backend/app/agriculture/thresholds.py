"""Loadable agricultural rule configuration.

Values are deliberately optional. They must be supplied and reviewed for the target
crop, soil, climate, and farm practice before being used in production.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CropProfile:
    minimum_temperature_celsius: float | None = None
    maximum_temperature_celsius: float | None = None
    minimum_humidity_percent: float | None = None
    maximum_humidity_percent: float | None = None
    maximum_wind_speed_kph_for_spraying: float | None = None


@dataclass(frozen=True)
class AgriculturalThresholds:
    irrigation_rainfall_lookahead_mm: float | None = None
    irrigation_soil_moisture_sufficient_percent: float | None = None
    spray_rainfall_lookahead_mm: float | None = None
    spray_min_humidity_percent: float | None = None
    spray_max_humidity_percent: float | None = None
    spray_max_wind_speed_kph: float | None = None
    sowing_min_temperature_celsius: float | None = None
    sowing_max_temperature_celsius: float | None = None
    sowing_rainfall_min_mm: float | None = None
    sowing_rainfall_max_mm: float | None = None
    extreme_temperature_low_celsius: float | None = None
    extreme_temperature_high_celsius: float | None = None
    extreme_rainfall_mm: float | None = None
    extreme_wind_speed_kph: float | None = None
    crop_profiles: dict[str, CropProfile] | None = None
    source_notes: dict[str, str] | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AgriculturalThresholds":
        profiles = {
            name.lower(): CropProfile(**values)
            for name, values in data.get("crop_profiles", {}).items()
        }
        values = {
            key: value
            for key, value in data.items()
            if key not in {"crop_profiles", "source_notes"}
        }
        return cls(
            **values,
            crop_profiles=profiles,
            source_notes=data.get("source_notes", {}),
        )

    @classmethod
    def from_json(cls, path: Path) -> "AgriculturalThresholds":
        return cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))


DEFAULT_THRESHOLDS_PATH = Path(__file__).with_name("data") / "agricultural_thresholds.json"


def load_default_thresholds() -> AgriculturalThresholds:
    return AgriculturalThresholds.from_json(DEFAULT_THRESHOLDS_PATH)
