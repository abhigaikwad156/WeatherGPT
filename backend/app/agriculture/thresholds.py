"""Loadable agricultural rule configuration.

Values are deliberately optional. They must be supplied and reviewed for the target
crop, soil, climate, and farm practice before being used in production.
"""

import json
import math
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
        return bool(
            self.source.publisher
            and self.source.document_title
            and self.source.reviewed_by
        ) and (
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
        thresholds = cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))
        thresholds.validate_configured_sources()
        return thresholds

    def validate_configured_sources(self) -> None:
        """Reject enabled rule values without traceable review notes or valid ranges."""
        notes = self.source_notes or {}
        scalar_fields = (
            "spray_rainfall_lookahead_mm",
            "spray_min_humidity_percent",
            "spray_max_humidity_percent",
            "spray_max_wind_speed_kph",
            "sowing_min_temperature_celsius",
            "sowing_max_temperature_celsius",
            "sowing_rainfall_min_mm",
            "sowing_rainfall_max_mm",
            "extreme_temperature_low_celsius",
            "extreme_temperature_high_celsius",
            "extreme_rainfall_mm",
            "extreme_wind_speed_kph",
        )
        for field_name in scalar_fields:
            value = getattr(self, field_name)
            if value is None:
                continue
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
            if not notes.get(field_name, "").strip():
                raise ValueError(f"source_notes.{field_name} is required for an enabled rule")
            if field_name.endswith("humidity_percent") and not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")
            if any(unit in field_name for unit in ("rainfall", "wind_speed")) and value < 0:
                raise ValueError(f"{field_name} cannot be negative")

        self._validate_ordered_range(
            self.spray_min_humidity_percent,
            self.spray_max_humidity_percent,
            "spray humidity",
        )
        self._validate_ordered_range(
            self.sowing_min_temperature_celsius,
            self.sowing_max_temperature_celsius,
            "sowing temperature",
        )
        self._validate_ordered_range(
            self.sowing_rainfall_min_mm,
            self.sowing_rainfall_max_mm,
            "sowing rainfall",
        )
        self._validate_ordered_range(
            self.extreme_temperature_low_celsius,
            self.extreme_temperature_high_celsius,
            "extreme temperature",
        )

        for crop, profile in (self.crop_profiles or {}).items():
            values = tuple(value for value in profile.__dict__.values() if value is not None)
            if not values:
                continue
            note_key = f"crop_profiles.{crop}"
            if not notes.get(note_key, "").strip():
                raise ValueError(f"source_notes.{note_key} is required for an enabled profile")
            if any(not math.isfinite(value) for value in values):
                raise ValueError(f"crop profile {crop!r} values must be finite")
            for field_name in (
                "minimum_humidity_percent",
                "maximum_humidity_percent",
            ):
                value = getattr(profile, field_name)
                if value is not None and not 0 <= value <= 100:
                    raise ValueError(
                        f"crop profile {crop!r} {field_name} must be between 0 and 100"
                    )
            self._validate_ordered_range(
                profile.minimum_temperature_celsius,
                profile.maximum_temperature_celsius,
                f"crop profile {crop} temperature",
            )
            self._validate_ordered_range(
                profile.minimum_humidity_percent,
                profile.maximum_humidity_percent,
                f"crop profile {crop} humidity",
            )

        for profile in self.irrigation_profiles:
            if not profile.is_reviewed():
                raise ValueError(
                    f"irrigation profile for {profile.crop!r} requires publisher, "
                    "document title, reviewer, and an eligible effective date"
                )
            moisture = profile.soil_moisture
            if moisture.sufficient_percent is not None:
                if not 0 <= moisture.sufficient_percent <= 100:
                    raise ValueError("irrigation soil-moisture threshold must be between 0 and 100")
                if not moisture.measurement_basis or not moisture.sensor_depth_cm:
                    raise ValueError(
                        "configured irrigation soil-moisture threshold requires measurement basis "
                        "and sensor depth"
                    )
                if not math.isfinite(moisture.sensor_depth_cm) or moisture.sensor_depth_cm <= 0:
                    raise ValueError("irrigation sensor depth must be positive and finite")
            forecast = profile.forecast
            if forecast.rainfall_lookahead_mm is not None:
                if (
                    not math.isfinite(forecast.rainfall_lookahead_mm)
                    or forecast.rainfall_lookahead_mm < 0
                ):
                    raise ValueError("irrigation forecast rainfall threshold must be non-negative")
                if forecast.horizon_days is None or forecast.horizon_days <= 0:
                    raise ValueError(
                        "configured irrigation forecast threshold requires a positive horizon"
                    )

    @staticmethod
    def _validate_ordered_range(
        minimum: float | None, maximum: float | None, label: str
    ) -> None:
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{label} minimum cannot exceed maximum")


DEFAULT_THRESHOLDS_PATH = Path(__file__).with_name("data") / "agricultural_thresholds.json"


def load_default_thresholds() -> AgriculturalThresholds:
    return AgriculturalThresholds.from_json(DEFAULT_THRESHOLDS_PATH)
