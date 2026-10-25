"""Generate persisted alerts from configured extreme-weather rules."""

import hashlib
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.extreme_weather import assess_extreme_weather
from app.agriculture.thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    AgriculturalThresholds,
    load_default_thresholds,
)
from app.agriculture.types import AgriculturalInputs, DecisionValue, WeatherSnapshot
from app.core.config import get_settings
from app.domain.models import AlertSeverity, Farm, WeatherAlert
from app.weather.types import NormalizedWeather


def generate_weather_alerts(
    session: Session,
    user_id: UUID,
    farm: Farm,
    weather: NormalizedWeather,
) -> list[WeatherAlert]:
    """Persist deduplicated alerts supported by current weather and configured rules."""
    if farm.owner_id != user_id or weather.farm_id != farm.id:
        raise ValueError("Weather alert generation requires the farm owner and its weather data")

    settings = get_settings()
    now = datetime.now(UTC)
    fetched_at = _as_utc(weather.fetched_at)
    if fetched_at is None or not timedelta(0) <= now - fetched_at <= timedelta(
        seconds=settings.weather_cache_ttl_seconds
    ):
        return []

    current = weather.current
    current_is_fresh = bool(
        current
        and (observed_at := _as_utc(current.observed_at)) is not None
        and timedelta(0)
        <= now - observed_at
        <= timedelta(seconds=settings.weather_cache_ttl_seconds)
    )
    current_temperature = (
        current.temperature_celsius if current_is_fresh and current else None
    )
    current_wind_speed = current.wind_speed_kph if current_is_fresh and current else None

    forecast_end = now + timedelta(days=3)
    forecast = [
        item
        for item in weather.daily
        if (forecast_at := _as_utc(item.forecast_for)) is not None
        and now <= forecast_at <= forecast_end
    ]
    forecast_rainfall = (
        sum(float(item.precipitation_mm) for item in forecast)
        if forecast and all(item.precipitation_mm is not None for item in forecast)
        else None
    )

    engine = _get_decision_engine()
    inputs = AgriculturalInputs(
        temperature_celsius=current_temperature,
        wind_speed_kph=current_wind_speed,
        forecast_rainfall_mm=forecast_rainfall,
    )
    candidates: list[tuple[str, str, str, datetime, datetime | None]] = []

    threshold_decision = assess_extreme_weather(inputs, engine.thresholds)
    if threshold_decision.decision == DecisionValue.HIGH_RISK:
        candidates.extend(
            (
                _alert_type("threshold", reason),
                "Extreme weather risk",
                reason,
                now,
                None,
            )
            for reason in threshold_decision.reasons
        )

    for event in weather.severe:
        starts_at = _as_utc(event.starts_at)
        ends_at = _as_utc(event.ends_at) if event.ends_at is not None else None
        if (
            starts_at is None
            or (ends_at is not None and ends_at <= now)
            or (ends_at is not None and ends_at < starts_at)
        ):
            continue
        severe_inputs = AgriculturalInputs(
            temperature_celsius=current_temperature,
            wind_speed_kph=current_wind_speed,
            forecast_rainfall_mm=forecast_rainfall,
            forecast_weather=(WeatherSnapshot(starts_at, severe_weather=True),),
        )
        decision = assess_extreme_weather(severe_inputs, engine.thresholds)
        if decision.decision == DecisionValue.HIGH_RISK:
            candidates.append(
                (
                    _alert_type("severe", event.title, event.description),
                    event.title,
                    event.description,
                    starts_at,
                    ends_at,
                )
            )

    if not candidates:
        return []

    active_alert_types = set(
        session.scalars(
            select(WeatherAlert.alert_type).where(
                WeatherAlert.user_id == user_id,
                WeatherAlert.farm_id == farm.id,
                or_(WeatherAlert.ends_at.is_(None), WeatherAlert.ends_at >= now),
            )
        ).all()
    )
    generated: list[WeatherAlert] = []
    for alert_type, title, body, starts_at, ends_at in candidates:
        if alert_type in active_alert_types:
            continue
        alert = WeatherAlert(
            user_id=user_id,
            farm_id=farm.id,
            farmer_crop_id=None,
            alert_type=alert_type,
            severity=AlertSeverity.HIGH,
            title=title,
            body=body,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        session.add(alert)
        active_alert_types.add(alert_type)
        generated.append(alert)
    return generated


def _get_decision_engine() -> AgriculturalDecisionEngine:
    configured_path = get_settings().agricultural_thresholds_path
    path = configured_path or DEFAULT_THRESHOLDS_PATH
    stat = path.stat()
    return _decision_engine_for_config(
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
        configured_path is None,
    )


@lru_cache(maxsize=8)
def _decision_engine_for_config(
    path: str,
    modified_at_ns: int,
    size_bytes: int,
    is_default: bool,
) -> AgriculturalDecisionEngine:
    """Reuse rule configuration until its selected file changes."""
    del modified_at_ns, size_bytes
    thresholds = (
        load_default_thresholds()
        if is_default
        else AgriculturalThresholds.from_json(Path(path))
    )
    return AgriculturalDecisionEngine(thresholds)


def _alert_type(category: str, *signals: str) -> str:
    fingerprint = hashlib.sha256("\0".join(signals).encode("utf-8")).hexdigest()[:32]
    return f"extreme_weather_{category}_{fingerprint}"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return None
    return value.astimezone(UTC)
