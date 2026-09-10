"""Verified weather data access used by conversational orchestration."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Farm, WeatherAlert, WeatherForecast, WeatherObservation


@dataclass(frozen=True)
class WeatherResult:
    intent: str
    farm_id: UUID
    farm_name: str
    current: dict[str, object] | None = None
    forecast: list[dict[str, object]] | None = None
    rainfall_mm: float | None = None
    alerts: list[dict[str, object]] | None = None
    source: str | None = None


class WeatherTool:
    """Read only verified weather records for a farmer-owned farm."""

    def __init__(self, session: Session, user_id: UUID, farm_id: UUID | None = None) -> None:
        self.session = session
        self.user_id = user_id
        self.farm_id = farm_id

    def _farm(self) -> Farm | None:
        statement = select(Farm).where(Farm.owner_id == self.user_id)
        if self.farm_id is not None:
            statement = statement.where(Farm.id == self.farm_id)
        return self.session.scalar(statement.order_by(Farm.created_at.asc()))

    def run(self, intent: str) -> WeatherResult | None:
        farm = self._farm()
        if farm is None:
            return None
        if intent == "CURRENT_WEATHER":
            return self.current_weather(farm)
        if intent == "FORECAST":
            return self.forecast(farm)
        if intent == "RAINFALL":
            return self.rainfall(farm)
        if intent == "WEATHER_ALERT":
            return self.alerts(farm)
        return None

    def current_weather(self, farm: Farm) -> WeatherResult:
        observation = self.session.scalar(
            select(WeatherObservation)
            .where(WeatherObservation.farm_id == farm.id)
            .order_by(WeatherObservation.observed_at.desc())
        )
        current = None
        source = None
        if observation is not None:
            current = {
                "observed_at": observation.observed_at,
                "temperature_celsius": observation.temperature_celsius,
                "humidity_percent": observation.humidity_percent,
                "rainfall_mm": observation.rainfall_mm,
                "wind_speed_kph": observation.wind_speed_kph,
            }
            source = observation.provider
        return WeatherResult("CURRENT_WEATHER", farm.id, farm.name, current=current, source=source)

    def forecast(self, farm: Farm) -> WeatherResult:
        now = datetime.now(UTC)
        forecasts = self.session.scalars(
            select(WeatherForecast)
            .where(
                WeatherForecast.farm_id == farm.id,
                WeatherForecast.forecast_for >= now,
                WeatherForecast.forecast_for <= now + timedelta(days=3),
            )
            .order_by(WeatherForecast.forecast_for.asc())
        ).all()
        return WeatherResult(
            "FORECAST",
            farm.id,
            farm.name,
            forecast=[
                {
                    "forecast_for": item.forecast_for,
                    "temperature_min_celsius": item.temperature_min_celsius,
                    "temperature_max_celsius": item.temperature_max_celsius,
                    "precipitation_mm": item.precipitation_mm,
                    "rain_probability_percent": item.rain_probability_percent,
                }
                for item in forecasts
            ],
            source=forecasts[0].provider if forecasts else None,
        )

    def rainfall(self, farm: Farm) -> WeatherResult:
        observation = self.session.scalar(
            select(WeatherObservation)
            .where(WeatherObservation.farm_id == farm.id)
            .order_by(WeatherObservation.observed_at.desc())
        )
        rainfall = (
            float(observation.rainfall_mm) if observation and observation.rainfall_mm else None
        )
        return WeatherResult(
            "RAINFALL",
            farm.id,
            farm.name,
            rainfall_mm=rainfall,
            source=observation.provider if observation else None,
        )

    def alerts(self, farm: Farm) -> WeatherResult:
        now = datetime.now(UTC)
        alerts = self.session.scalars(
            select(WeatherAlert)
            .where(
                WeatherAlert.user_id == self.user_id,
                WeatherAlert.farm_id == farm.id,
                WeatherAlert.starts_at <= now,
                (WeatherAlert.ends_at.is_(None) | (WeatherAlert.ends_at >= now)),
            )
            .order_by(WeatherAlert.starts_at.desc())
        ).all()
        return WeatherResult(
            "WEATHER_ALERT",
            farm.id,
            farm.name,
            alerts=[
                {
                    "id": item.id,
                    "severity": item.severity.value,
                    "title": item.title,
                    "body": item.body,
                    "starts_at": item.starts_at,
                    "ends_at": item.ends_at,
                }
                for item in alerts
            ],
        )
