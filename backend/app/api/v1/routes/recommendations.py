"""Authenticated read-only deterministic agricultural recommendations."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.domain.models import Farm
from app.schemas.recommendations import RecommendationsResponse
from app.services.recommendations import (
    build_recommendations_response,
    create_decision_engine,
)
from app.weather.factory import build_cache, build_provider
from app.weather.providers import WeatherProviderError
from app.weather.service import WeatherService

router = APIRouter(prefix="/recommendations")


@router.get("", response_model=RecommendationsResponse)
def get_recommendations(user: CurrentUser, session: DatabaseSession) -> RecommendationsResponse:
    """Compute current decisions from the authenticated user's own farms and weather."""
    farms = session.scalars(
        select(Farm).where(Farm.owner_id == user.id).order_by(Farm.created_at)
    ).all()
    if not farms:
        return RecommendationsResponse(
            status="insufficient_data",
            message="Add a farm with its location before requesting recommendations.",
            farms=[],
        )

    try:
        settings = get_settings()
        weather_service = WeatherService(
            session, build_provider(settings), build_cache(settings)
        )
        weather_by_farm = {}
        for farm in farms:
            weather_by_farm[farm.id] = weather_service.get_weather(farm, refresh=True)
    except WeatherProviderError as error:
        raise HTTPException(
            status_code=503,
            detail="Current farm weather is unavailable; recommendations were not generated.",
        ) from error

    response = build_recommendations_response(
        session, user.id, farms, weather_by_farm, create_decision_engine()
    )
    session.commit()
    return response
