"""Authenticated weather alert endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.domain.models import WeatherAlert
from app.schemas.dashboard import DashboardAlert

router = APIRouter()


@router.get("/weather-alerts", response_model=list[DashboardAlert])
def read_weather_alerts(user: CurrentUser, session: DatabaseSession) -> list[WeatherAlert]:
    """Return persisted, active, unacknowledged alerts for the current user."""
    now = datetime.now(UTC)
    return list(
        session.scalars(
            select(WeatherAlert)
            .where(
                WeatherAlert.user_id == user.id,
                WeatherAlert.starts_at <= now,
                WeatherAlert.acknowledged_at.is_(None),
                or_(WeatherAlert.ends_at.is_(None), WeatherAlert.ends_at >= now),
            )
            .order_by(WeatherAlert.starts_at.desc())
        ).all()
    )
