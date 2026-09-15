"""Database-backed tools used by the agricultural conversation pipeline."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.conversation.agricultural_pipeline import FarmerContext, WeatherContext
from app.domain.models import Crop, Farm, FarmerCrop, WeatherForecast, WeatherObservation


class DatabaseFarmerContextTool:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_context(
        self, user_id: UUID, farm_id: UUID | None, crop: str | None
    ) -> FarmerContext | None:
        statement = (
            select(Farm, FarmerCrop, Crop)
            .outerjoin(
                FarmerCrop,
                and_(
                    FarmerCrop.farm_id == Farm.id,
                    FarmerCrop.is_active.is_(True),
                ),
            )
            .outerjoin(Crop, Crop.id == FarmerCrop.crop_id)
            .where(Farm.owner_id == user_id)
        )
        if farm_id is not None:
            statement = statement.where(Farm.id == farm_id)
        if crop is not None:
            statement = statement.where(Crop.name.ilike(crop))
        row = self.session.execute(statement.order_by(Farm.created_at.asc())).first()
        if row is None:
            return None
        farm, farmer_crop, crop_record = row
        return FarmerContext(
            farm.id,
            farm.name,
            None,
            farm.soil_type,
            farm.irrigation_type,
            float(farm.soil_moisture_percent) if farm.soil_moisture_percent is not None else None,
            crop_record.name if crop_record is not None else None,
            farmer_crop.growth_stage if farmer_crop is not None else None,
        )


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
            recent_rainfall_mm=float(observation.rainfall_mm)
            if observation and observation.rainfall_mm is not None
            else None,
            forecast_rainfall_mm=(
                float(forecasts[0].precipitation_mm)
                if forecasts and forecasts[0].precipitation_mm is not None
                else None
            ),
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
        )
