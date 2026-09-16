"""Database-backed tools used by the agricultural conversation pipeline."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.agriculture.types import WeatherSnapshot
from app.conversation.agricultural_pipeline import FarmerContext, WeatherContext
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
        return FarmerContext(
            farm.id,
            farm.name,
            user.location or f"{farm.latitude}, {farm.longitude}",
            farm.soil_type,
            farm.irrigation_type,
            float(farm.soil_moisture_percent) if farm.soil_moisture_percent is not None else None,
            crop_record.name if crop_record is not None else None,
            farmer_crop.growth_stage if farmer_crop is not None else None,
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

    def get_context(self, farm_id: UUID) -> WeatherContext:
        now = datetime.now(UTC)
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
                WeatherForecast.forecast_for <= now + timedelta(days=3),
            )
            .order_by(WeatherForecast.forecast_for.asc())
        ).all()
        return WeatherContext(
            recent_rainfall_mm=_sum_or_none(item.rainfall_mm for item in observations),
            forecast_rainfall_mm=_sum_or_none(item.precipitation_mm for item in forecasts),
            temperature_celsius=(
                float(observation.temperature_celsius)
                if observation and observation.temperature_celsius is not None
                else None
            ),
            humidity_percent=(
                float(observation.humidity_percent)
                if observation and observation.humidity_percent is not None
                else None
            ),
            wind_speed_kph=(
                float(observation.wind_speed_kph)
                if observation and observation.wind_speed_kph is not None
                else None
            ),
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
                for item in forecasts
            ),
        )


def _sum_or_none(values: object) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return sum(numeric) if numeric else None


def _average_or_none(*values: object) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return sum(numeric) / len(numeric) if numeric else None
