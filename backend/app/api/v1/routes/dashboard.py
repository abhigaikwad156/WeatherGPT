"""Authenticated aggregated dashboard endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.domain.models import Farm, FarmerCrop, Recommendation, WeatherAlert
from app.schemas.dashboard import (
    DashboardAlert,
    DashboardCrop,
    DashboardForecast,
    DashboardRecommendation,
    DashboardResponse,
    DashboardWeather,
)
from app.weather.factory import build_cache, build_provider
from app.weather.service import WeatherService

router = APIRouter(prefix="/dashboard")


@router.get("", response_model=DashboardResponse)
def read_dashboard(user: CurrentUser, session: DatabaseSession) -> DashboardResponse:
    """Return the first owned farm's data in the shape used by the frontend."""
    farm = session.scalar(
        select(Farm).where(Farm.owner_id == user.id).order_by(Farm.created_at)
    )
    if farm is None:
        return DashboardResponse(
            current_weather=None,
            forecast=[],
            active_alerts=[],
            current_crop=None,
            recommended_actions=[],
            upcoming_risks=[],
        )

    settings = get_settings()
    weather = WeatherService(
        session, build_provider(settings), build_cache(settings)
    ).get_weather(farm)
    now = datetime.now(UTC)

    crop = session.scalar(
        select(FarmerCrop)
        .options(joinedload(FarmerCrop.crop))
        .where(
            FarmerCrop.farm_id == farm.id,
            FarmerCrop.farmer_id == user.id,
            FarmerCrop.is_active.is_(True),
        )
        .order_by(FarmerCrop.created_at.desc())
    )
    alerts = session.scalars(
        select(WeatherAlert)
        .where(
            WeatherAlert.user_id == user.id,
            WeatherAlert.farm_id == farm.id,
            WeatherAlert.acknowledged_at.is_(None),
            or_(WeatherAlert.ends_at.is_(None), WeatherAlert.ends_at >= now),
        )
        .order_by(WeatherAlert.starts_at)
    ).all()
    recommendations = session.scalars(
        select(Recommendation)
        .where(Recommendation.user_id == user.id, Recommendation.farm_id == farm.id)
        .order_by(Recommendation.generated_at.desc())
        .limit(10)
    ).all()

    def alert_response(alert: WeatherAlert) -> DashboardAlert:
        return DashboardAlert.model_validate(alert, from_attributes=True)

    return DashboardResponse(
        current_weather=DashboardWeather(
            temperature_celsius=weather.current.temperature_celsius if weather.current else None,
            condition=weather.current.condition if weather.current else None,
            rainfall_mm=weather.current.rainfall_mm if weather.current else None,
            observed_at=weather.current.observed_at if weather.current else None,
        ),
        forecast=[
            DashboardForecast(
                forecast_for=item.forecast_for,
                temperature_min_celsius=item.temperature_min_celsius,
                temperature_max_celsius=item.temperature_max_celsius,
                precipitation_mm=item.precipitation_mm,
                rain_probability_percent=item.rain_probability_percent,
            )
            for item in weather.daily
        ],
        active_alerts=[alert_response(alert) for alert in alerts],
        current_crop=(
            DashboardCrop(name=crop.crop.name, growth_stage=crop.growth_stage)
            if crop is not None
            else None
        ),
        recommended_actions=[
            DashboardRecommendation.model_validate(item, from_attributes=True)
            for item in recommendations
        ],
        upcoming_risks=[alert_response(alert) for alert in alerts],
    )
