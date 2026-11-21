"""Database-backed tools used by the agricultural conversation pipeline."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.agriculture.types import WeatherSnapshot
from app.conversation.agricultural_pipeline import FarmerContext, WeatherContext
from app.core.config import get_settings
from app.domain.models import Crop, Farm, FarmerCrop, User, WeatherForecast, WeatherObservation


class DatabaseFarmerContextTool:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_context(
        self, user_id: UUID, farm_id: UUID | None, crop: str | None
    ) -> FarmerContext | None:
        statement = (
            select(Farm, FarmerCrop, Crop, User)
            .outerjoin(
                FarmerCrop,
                and_(
                    FarmerCrop.farm_id == Farm.id,
                    FarmerCrop.farmer_id == user_id,
                    FarmerCrop.is_active.is_(True),
                ),
            )
            .outerjoin(Crop, Crop.id == FarmerCrop.crop_id)
            .join(User, User.id == Farm.owner_id)
            .where(Farm.owner_id == user_id)
        )
        if farm_id is not None:
            statement = statement.where(Farm.id == farm_id)
        if crop is not None:
            statement = statement.where(Crop.name.ilike(crop))
        row = self.session.execute(statement.order_by(Farm.created_at.asc())).first()
        if row is None:
            return None
        farm, farmer_crop, crop_record, user = row
        today = datetime.now(UTC).date()
        return FarmerContext(
            farm.id,
            farm.name,
            farm.location_name or user.location,
            farm.soil_type,
            farm.irrigation_type,
            float(farm.soil_moisture_percent) if farm.soil_moisture_percent is not None else None,
            crop_record.name if crop_record is not None else None,
            farmer_crop.growth_stage if farmer_crop is not None else None,
            (
                (datetime.now(UTC).date() - farmer_crop.planted_at).days
                if farmer_crop is not None
                and farmer_crop.planted_at is not None
                and farmer_crop.planted_at <= today
                else None
            ),
            farm.soil_moisture_measured_at,
            farmer_crop.last_irrigated_at if farmer_crop is not None else None,
            farm.irrigation_layout,
            farm.irrigation_configuration,
            farmer_crop.id if farmer_crop is not None else None,
            farm.region,
        )

    def list_crops(self, user_id: UUID, farm_id: UUID | None) -> tuple[str, ...]:
        statement = (
            select(Crop.name)
            .join(FarmerCrop, FarmerCrop.crop_id == Crop.id)
            .join(Farm, Farm.id == FarmerCrop.farm_id)
            .where(
                Farm.owner_id == user_id,
                FarmerCrop.farmer_id == user_id,
                FarmerCrop.is_active.is_(True),
            )
        )
        if farm_id is not None:
            statement = statement.where(Farm.id == farm_id)
        return tuple(self.session.scalars(statement.order_by(Crop.name.asc())).all())


class DatabaseWeatherContextTool:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_context(self, farm_id: UUID, *, forecast_horizon_days: int = 3) -> WeatherContext:
        if forecast_horizon_days <= 0:
            raise ValueError("forecast_horizon_days must be positive")
        now = datetime.now(UTC)
        max_age = timedelta(seconds=get_settings().weather_cache_ttl_seconds)
        observation = self.session.scalar(
            select(WeatherObservation)
            .where(WeatherObservation.farm_id == farm_id)
            .order_by(WeatherObservation.observed_at.desc())
        )
        observations = self.session.scalars(
            select(WeatherObservation)
            .where(
                WeatherObservation.farm_id == farm_id,
                WeatherObservation.observed_at >= now - timedelta(days=3),
            )
            .order_by(WeatherObservation.observed_at.asc())
        ).all()
        forecasts = self.session.scalars(
            select(WeatherForecast)
            .where(
                WeatherForecast.farm_id == farm_id,
                WeatherForecast.forecast_for >= now,
                WeatherForecast.forecast_for <= now + timedelta(days=forecast_horizon_days),
                WeatherForecast.issued_at >= now - max_age,
                WeatherForecast.issued_at <= now,
            )
            .order_by(WeatherForecast.forecast_for.asc())
        ).all()
        forecast_by_date: dict[date, WeatherForecast] = {}
        for item in forecasts:
            forecast_date = item.forecast_for.date()
            existing = forecast_by_date.get(forecast_date)
            if existing is None or item.issued_at > existing.issued_at:
                forecast_by_date[forecast_date] = item
        expected_dates = {
            (now + timedelta(days=offset)).date() for offset in range(1, forecast_horizon_days + 1)
        }
        complete_forecast = all(
            day in forecast_by_date and forecast_by_date[day].precipitation_mm is not None
            for day in expected_dates
        )
        rainfall_forecast = (
            sum(float(forecast_by_date[day].precipitation_mm) for day in expected_dates)
            if complete_forecast
            else None
        )
        current_observation = (
            observation
            if observation
            and observation.observed_at.tzinfo is not None
            and now - max_age <= observation.observed_at <= now
            else None
        )
        return WeatherContext(
            recent_rainfall_mm=_sum_or_none(item.rainfall_mm for item in observations),
            forecast_rainfall_mm=rainfall_forecast,
            temperature_celsius=(
                float(current_observation.temperature_celsius)
                if current_observation and current_observation.temperature_celsius is not None
                else None
            ),
            humidity_percent=(
                float(current_observation.humidity_percent)
                if current_observation and current_observation.humidity_percent is not None
                else None
            ),
            wind_speed_kph=(
                float(current_observation.wind_speed_kph)
                if current_observation and current_observation.wind_speed_kph is not None
                else None
            ),
            forecast_horizon_days=forecast_horizon_days,
            historical_weather=tuple(
                WeatherSnapshot(
                    item.observed_at,
                    rainfall_mm=float(item.rainfall_mm) if item.rainfall_mm is not None else None,
                    temperature_celsius=(
                        float(item.temperature_celsius)
                        if item.temperature_celsius is not None
                        else None
                    ),
                    humidity_percent=(
                        float(item.humidity_percent) if item.humidity_percent is not None else None
                    ),
                    wind_speed_kph=(
                        float(item.wind_speed_kph) if item.wind_speed_kph is not None else None
                    ),
                    condition=item.condition,
                )
                for item in observations
            ),
            forecast_weather=tuple(
                WeatherSnapshot(
                    item.forecast_for,
                    rainfall_mm=(
                        float(item.precipitation_mm) if item.precipitation_mm is not None else None
                    ),
                    temperature_celsius=_average_or_none(
                        item.temperature_min_celsius, item.temperature_max_celsius
                    ),
                    condition=item.condition,
                )
                for item in forecast_by_date.values()
                if item.forecast_for.date() in expected_dates
            ),
        )


def _sum_or_none(values: object) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return sum(numeric) if numeric else None


def _average_or_none(*values: object) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return sum(numeric) / len(numeric) if numeric else None
