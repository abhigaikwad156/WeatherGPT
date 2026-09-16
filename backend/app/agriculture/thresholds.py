"""Loadable agricultural rule configuration.

Values are deliberately optional. They must be supplied and reviewed for the target
crop, soil, climate, and farm practice before being used in production.
"""

import json
from dataclasses import dataclass
from datetime import date
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
class IrrigationSoilMoisture:
    """The sensor contract used by a reviewed irrigation profile."""

    sufficient_percent: float | None = None
    measurement_basis: str | None = None
    sensor_depth_cm: float | None = None


@dataclass(frozen=True)
class IrrigationForecast:
    """Forecast contract used by a reviewed irrigation profile."""

    rainfall_lookahead_mm: float | None = None
    horizon_days: int | None = None


@dataclass(frozen=True)
class IrrigationProfileSource:
    """Provenance required to review an irrigation profile."""

    publisher: str | None = None
    document_title: str | None = None
    source_uri: str | None = None
    reviewed_by: str | None = None
    effective_from: date | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "IrrigationProfileSource":
        values = dict(data)
        effective_from = values.get("effective_from")
        if effective_from is not None:
            values["effective_from"] = date.fromisoformat(effective_from)
        return cls(**values)


@dataclass(frozen=True)
class IrrigationProfile:
    """A crop-specific, source-bearing irrigation decision profile.

    `None` on a matching dimension means that profile accepts any value for that
    dimension; crop itself is always required. It is not a global fallback,
    because a profile can never match a different crop.
    """

    crop: str
    growth_stage: str | None = None
    soil_type: str | None = None
    irrigation_type: str | None = None
    region: str | None = None
    soil_moisture: IrrigationSoilMoisture = IrrigationSoilMoisture()
    forecast: IrrigationForecast = IrrigationForecast()
    source: IrrigationProfileSource = IrrigationProfileSource()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "IrrigationProfile":
        values = dict(data)
        values["soil_moisture"] = IrrigationSoilMoisture(
            **values.get("soil_moisture", {})
        )
        values["forecast"] = IrrigationForecast(**values.get("forecast", {}))
        values["source"] = IrrigationProfileSource.from_mapping(values.get("source", {}))
        return cls(**values)

    def specificity(self) -> int:
        return sum(
            value is not None
            for value in (self.growth_stage, self.soil_type, self.irrigation_type, self.region)
        )

    def is_reviewed(self) -> bool:
        return bool(self.source.reviewed_by) and (
            self.source.effective_from is None or self.source.effective_from <= date.today()
        )


@dataclass(frozen=True)
class AgriculturalThresholds:
    irrigation_profiles: tuple[IrrigationProfile, ...] = ()
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
            if key not in {"crop_profiles", "irrigation_profiles", "source_notes"}
        }
        return cls(
            **values,
            crop_profiles=profiles,
            irrigation_profiles=tuple(
                IrrigationProfile.from_mapping(profile)
                for profile in data.get("irrigation_profiles", [])
            ),
            source_notes=data.get("source_notes", {}),
        )

    @classmethod
    def from_json(cls, path: Path) -> "AgriculturalThresholds":
        return cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))


DEFAULT_THRESHOLDS_PATH = Path(__file__).with_name("data") / "agricultural_thresholds.json"


def load_default_thresholds() -> AgriculturalThresholds:
    return AgriculturalThresholds.from_json(DEFAULT_THRESHOLDS_PATH)
