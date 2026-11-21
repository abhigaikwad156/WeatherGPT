"""Deterministic recommendations computed from owned farm data and reviewed rules."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.irrigation import matching_irrigation_profile
from app.agriculture.rules import missing_decision
from app.agriculture.thresholds import AgriculturalThresholds, load_default_thresholds
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
    WeatherSnapshot,
)
from app.core.config import get_settings
from app.domain.models import (
    Farm,
    FarmerCrop,
    Recommendation,
    RecommendationStatus,
)
from app.schemas.recommendations import (
    DecisionRecommendation,
    FarmRecommendations,
    RecommendationsResponse,
)
from app.weather.types import NormalizedWeather


def create_decision_engine() -> AgriculturalDecisionEngine:
    path = get_settings().agricultural_thresholds_path
    thresholds = AgriculturalThresholds.from_json(path) if path else load_default_thresholds()
    return AgriculturalDecisionEngine(thresholds)


def build_recommendations_response(
    session: Session,
    user_id: UUID,
    farms: list[Farm],
    weather_by_farm: dict[UUID, NormalizedWeather],
    engine: AgriculturalDecisionEngine,
    *,
    now: datetime | None = None,
) -> RecommendationsResponse:
    """Build rule results only for farms supplied by an ownership-filtered query."""
    current_time = now or datetime.now(UTC)
    results = [
        build_farm_recommendations(
            session,
            user_id,
            farm,
            weather_by_farm[farm.id],
            engine,
            current_time=current_time,
        )
        for farm in farms
    ]
    has_available = any(
        item.status == "available" for farm in results for item in farm.recommendations
    )
    if not farms:
        return RecommendationsResponse(
            status="insufficient_data",
            message="Add a farm with its location before requesting recommendations.",
            farms=[],
        )
    return RecommendationsResponse(
        status="available" if has_available else "insufficient_data",
        message=(
            None
            if has_available
            else "No rule-based decision is available yet. Review the missing inputs below "
            "and ensure applicable agricultural thresholds are configured and reviewed."
        ),
        farms=results,
    )


def build_farm_recommendations(
    session: Session,
    user_id: UUID,
    farm: Farm,
    weather: NormalizedWeather,
    engine: AgriculturalDecisionEngine,
    *,
    current_time: datetime | None = None,
) -> FarmRecommendations:
    """Evaluate existing decision rules for each active crop, or farm-wide if none exists."""
    if farm.owner_id != user_id:
        raise ValueError("Recommendations require a farm owned by the authenticated user")
    if weather.farm_id != farm.id:
        raise ValueError("Weather data does not belong to the requested farm")

    now = current_time or datetime.now(UTC)
    settings = get_settings()
    max_age = timedelta(seconds=settings.weather_cache_ttl_seconds)
    current_is_fresh = (
        weather.fetched_at.tzinfo is not None
        and now - max_age <= weather.fetched_at <= now
        and weather.current is not None
        and weather.current.observed_at.tzinfo is not None
        and now - max_age <= weather.current.observed_at <= now
    )
    forecasts_are_fresh = (
        weather.fetched_at.tzinfo is not None and now - max_age <= weather.fetched_at <= now
    )

    crops = session.scalars(
        select(FarmerCrop)
        .options(joinedload(FarmerCrop.crop))
        .where(
            FarmerCrop.farm_id == farm.id,
            FarmerCrop.farmer_id == user_id,
            FarmerCrop.is_active.is_(True),
        )
        .order_by(FarmerCrop.created_at.desc())
    ).all()
    crop_records: list[FarmerCrop | None] = crops or [None]
    outputs: list[DecisionRecommendation] = []

    for crop_record in crop_records:
        crop_name = crop_record.crop.name if crop_record is not None else None
        inputs = _agricultural_inputs(
            farm,
            crop_record,
            weather,
            engine,
            now=now,
            include_current=current_is_fresh,
            include_forecast=forecasts_are_fresh,
        )
        for decision_type, decision in engine.evaluate(inputs).items():
            if decision_type == DecisionType.EXTREME_WEATHER:
                decision = _require_extreme_weather_inputs(decision, inputs, engine.thresholds)
            elif decision_type == DecisionType.SPRAYING:
                decision = _require_spraying_forecast(decision, inputs, engine.thresholds)
            recommendation = DecisionRecommendation(
                id=(f"{farm.id}:{crop_record.id if crop_record else 'farm'}:{decision_type.value}"),
                recommendation_type=decision_type.value,
                crop_id=crop_record.id if crop_record else None,
                crop_name=crop_name,
                decision=decision.decision.value,
                risk_level=decision.risk_level.value,
                confidence=decision.confidence,
                status=(
                    "needs_input" if decision.decision == DecisionValue.NEEDS_INPUT else "available"
                ),
                reasons=list(decision.reasons),
                applicable_crop_stage=decision.metadata.get("applicable_crop_stage"),
                crop_age_days=decision.metadata.get("crop_age_days"),
                source=decision.metadata.get("source"),
                evidence=decision.metadata.get("evidence", []),
                explanations=decision.explanations,
                data_basis=decision.metadata.get("data_basis"),
                weather_limitations=decision.metadata.get("weather_limitations", []),
                schedule_interval_days=decision.metadata.get("schedule_interval_days"),
                missing_inputs=decision.metadata.get("missing_inputs", []),
            )
            outputs.append(recommendation)
            if decision_type == DecisionType.IRRIGATION:
                persist_irrigation_recommendation(
                    session,
                    user_id,
                    farm.id,
                    crop_record.id if crop_record else None,
                    decision,
                    generated_at=now,
                )

    status = (
        "available" if any(item.status == "available" for item in outputs) else "insufficient_data"
    )
    return FarmRecommendations(
        farm_id=farm.id,
        farm_name=farm.name,
        weather_provider=weather.provider,
        weather_fetched_at=weather.fetched_at,
        status=status,
        recommendations=outputs,
    )


def _require_extreme_weather_inputs(
    decision: Decision,
    inputs: AgriculturalInputs,
    thresholds: AgriculturalThresholds,
) -> Decision:
    if decision.decision != DecisionValue.LOW_RISK:
        return decision

    missing: list[str] = []
    if (
        thresholds.extreme_temperature_low_celsius is not None
        or thresholds.extreme_temperature_high_celsius is not None
    ) and inputs.temperature_celsius is None:
        missing.append("Current temperature is required by the configured extreme-weather rule")
    if thresholds.extreme_rainfall_mm is not None and inputs.forecast_rainfall_mm is None:
        missing.append("Forecast rainfall is required by the configured extreme-weather rule")
    if thresholds.extreme_wind_speed_kph is not None and inputs.wind_speed_kph is None:
        missing.append("Current wind speed is required by the configured extreme-weather rule")
    if not missing:
        return decision
    return Decision(
        DecisionType.EXTREME_WEATHER,
        DecisionValue.NEEDS_INPUT,
        RiskLevel.UNKNOWN,
        0.0,
        tuple(missing),
    )


def _require_spraying_forecast(
    decision: Decision,
    inputs: AgriculturalInputs,
    thresholds: AgriculturalThresholds,
) -> Decision:
    if (
        decision.decision == DecisionValue.APPLY
        and thresholds.spray_rainfall_lookahead_mm is not None
        and inputs.forecast_rainfall_mm is None
    ):
        return missing_decision(
            DecisionType.SPRAYING,
            "Forecast rainfall is required by the configured spraying rule",
        )
    return decision


def available_dashboard_recommendations(
    results: list[FarmRecommendations],
) -> list[dict[str, object]]:
    """Expose deterministic decisions and irrigation inputs needed on the dashboard."""
    return [
        {
            "id": item.id,
            "recommendation_type": item.recommendation_type,
            "status": item.status,
            "summary": f"{item.decision}: {'; '.join(item.reasons)}",
            "decision_version": "deterministic-rules-v2",
            "decision": item.decision,
            "reasons": item.reasons,
            "applicable_crop_stage": item.applicable_crop_stage,
            "crop_age_days": item.crop_age_days,
            "source": item.source.model_dump() if item.source is not None else None,
            "evidence": [entry.model_dump() for entry in item.evidence],
            "explanations": item.explanations,
            "data_basis": item.data_basis,
            "weather_limitations": item.weather_limitations,
            "schedule_interval_days": item.schedule_interval_days,
            "missing_inputs": item.missing_inputs,
        }
        for farm in results
        for item in farm.recommendations
        if item.status == "available"
        or (
            item.recommendation_type == DecisionType.IRRIGATION.value
            and item.status == "needs_input"
        )
    ]


def _agricultural_inputs(
    farm: Farm,
    crop: FarmerCrop | None,
    weather: NormalizedWeather,
    engine: AgriculturalDecisionEngine,
    *,
    now: datetime,
    include_current: bool,
    include_forecast: bool,
) -> AgriculturalInputs:
    crop_name = crop.crop.name if crop is not None else None
    base = AgriculturalInputs(
        crop=crop_name,
        growth_stage=crop.growth_stage if crop is not None else None,
        crop_age_days=(
            (now.date() - crop.planted_at).days
            if crop is not None and crop.planted_at is not None and crop.planted_at <= now.date()
            else None
        ),
        soil_type=farm.soil_type,
        irrigation_type=farm.irrigation_type,
        region=farm.region,
        soil_moisture_percent=(
            float(farm.soil_moisture_percent) if farm.soil_moisture_percent is not None else None
        ),
        soil_moisture_measured_at=farm.soil_moisture_measured_at,
        last_irrigated_at=crop.last_irrigated_at if crop is not None else None,
        irrigation_layout=farm.irrigation_layout,
        irrigation_configuration=farm.irrigation_configuration,
        evaluation_time=now,
        historical_weather=_historical_weather(weather, now),
    )
    profile = matching_irrigation_profile(base, engine.thresholds)
    horizon_days = profile.forecast.horizon_days if profile else 3
    if horizon_days is None or horizon_days <= 0:
        horizon_days = 3

    cutoff = now + timedelta(days=horizon_days)
    forecasts = (
        tuple(
            WeatherSnapshot(
                timestamp=item.forecast_for,
                rainfall_mm=item.precipitation_mm,
                temperature_celsius=_average(
                    item.temperature_min_celsius, item.temperature_max_celsius
                ),
                condition=item.condition,
            )
            for item in weather.daily
            if now <= item.forecast_for <= cutoff
        )
        if include_forecast
        else ()
    )
    severe = tuple(
        WeatherSnapshot(
            timestamp=item.starts_at,
            condition=item.title,
            severe_weather=True,
        )
        for item in weather.severe
        if include_forecast
        and item.starts_at <= cutoff
        and (item.starts_at >= now or (item.ends_at is not None and item.ends_at >= now))
        and (item.ends_at is None or item.ends_at >= item.starts_at)
    )
    recent_rainfall = [
        item.rainfall_mm
        for item in _historical_weather(weather, now)
        if item.rainfall_mm is not None
    ]
    current = weather.current if include_current else None
    return AgriculturalInputs(
        crop=base.crop,
        growth_stage=base.growth_stage,
        crop_age_days=base.crop_age_days,
        soil_type=base.soil_type,
        irrigation_type=base.irrigation_type,
        region=base.region,
        recent_rainfall_mm=sum(recent_rainfall) if recent_rainfall else None,
        forecast_rainfall_mm=_complete_forecast_rainfall(
            forecasts, now=now, horizon_days=horizon_days
        ),
        forecast_horizon_days=horizon_days,
        temperature_celsius=current.temperature_celsius if current else None,
        humidity_percent=current.humidity_percent if current else None,
        wind_speed_kph=current.wind_speed_kph if current else None,
        soil_moisture_percent=base.soil_moisture_percent,
        soil_moisture_measured_at=base.soil_moisture_measured_at,
        last_irrigated_at=base.last_irrigated_at,
        irrigation_layout=base.irrigation_layout,
        irrigation_configuration=base.irrigation_configuration,
        evaluation_time=base.evaluation_time,
        historical_weather=base.historical_weather,
        forecast_weather=forecasts + severe,
    )


def _historical_weather(weather: NormalizedWeather, now: datetime) -> tuple[WeatherSnapshot, ...]:
    start = now - timedelta(days=3)
    return tuple(
        WeatherSnapshot(
            timestamp=item.observed_at,
            rainfall_mm=item.rainfall_mm,
            temperature_celsius=item.temperature_celsius,
            humidity_percent=item.humidity_percent,
            wind_speed_kph=item.wind_speed_kph,
            condition=item.condition,
        )
        for item in weather.hourly
        if start <= item.observed_at <= now
    )


def _average(first: float | None, second: float | None) -> float | None:
    values = [value for value in (first, second) if value is not None]
    return sum(values) / len(values) if values else None


def _complete_forecast_rainfall(
    forecasts: tuple[WeatherSnapshot, ...], *, now: datetime, horizon_days: int
) -> float | None:
    expected_dates = {
        (now + timedelta(days=offset)).date() for offset in range(1, horizon_days + 1)
    }
    rainfall_by_date = {
        item.timestamp.date(): item.rainfall_mm
        for item in forecasts
        if item.timestamp.date() in expected_dates
    }
    if set(rainfall_by_date) != expected_dates or any(
        rainfall_by_date[day] is None for day in expected_dates
    ):
        return None
    return sum(value for value in rainfall_by_date.values() if value is not None)


def persist_irrigation_recommendation(
    session: Session,
    user_id: UUID,
    farm_id: UUID,
    farmer_crop_id: UUID | None,
    decision: Decision,
    *,
    generated_at: datetime | None = None,
) -> Recommendation:
    """Upsert the latest deterministic irrigation decision for one farm/crop."""
    statement = (
        select(Recommendation)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.farm_id == farm_id,
            Recommendation.farmer_crop_id == farmer_crop_id
            if farmer_crop_id is not None
            else Recommendation.farmer_crop_id.is_(None),
            Recommendation.recommendation_type == DecisionType.IRRIGATION.value,
        )
        .order_by(Recommendation.generated_at.desc())
    )
    record = session.scalar(statement)
    created_at = generated_at or datetime.now(UTC)
    status = (
        RecommendationStatus.NEEDS_INPUT
        if decision.decision == DecisionValue.NEEDS_INPUT
        else RecommendationStatus.AVAILABLE
    )
    details: dict[str, object] = {
        "decision": decision.decision.value,
        "risk_level": decision.risk_level.value,
        "confidence": decision.confidence,
        "reasons": list(decision.reasons),
        "applicable_crop_stage": decision.metadata.get("applicable_crop_stage"),
        "crop_age_days": decision.metadata.get("crop_age_days"),
        "source": decision.metadata.get("source"),
        "evidence": decision.metadata.get("evidence", []),
        "missing_inputs": decision.metadata.get("missing_inputs", []),
        "explanations": decision.explanations,
        "data_basis": decision.metadata.get("data_basis"),
        "weather_limitations": decision.metadata.get("weather_limitations", []),
        "schedule_interval_days": decision.metadata.get("schedule_interval_days"),
    }
    summary = f"{decision.decision.value}: {'; '.join(decision.reasons)}"
    if record is None:
        record = Recommendation(
            user_id=user_id,
            farm_id=farm_id,
            farmer_crop_id=farmer_crop_id,
            recommendation_type=DecisionType.IRRIGATION.value,
            status=status,
            summary=summary,
            details=details,
            decision_version="irrigation-rules-v2",
            generated_at=created_at,
        )
        session.add(record)
    else:
        record.status = status
        record.summary = summary
        record.details = details
        record.decision_version = "irrigation-rules-v2"
        record.generated_at = created_at
    return record
