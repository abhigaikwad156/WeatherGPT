"""Provider-independent weather endpoints."""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.schemas.weather import WeatherResponse
from app.services.profiles import get_owned_farm
from app.weather.factory import build_cache, build_provider
from app.weather.service import WeatherService

router = APIRouter(prefix="/farms")


@router.get("/{farm_id}/weather", response_model=WeatherResponse)
def read_farm_weather(
    farm_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    refresh: bool = Query(default=False),
) -> WeatherResponse:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    settings = get_settings()
    weather = WeatherService(
        session,
        build_provider(settings),
        build_cache(settings),
    ).get_weather(farm, refresh=refresh)
    session.commit()
    return WeatherResponse.model_validate(asdict(weather))
