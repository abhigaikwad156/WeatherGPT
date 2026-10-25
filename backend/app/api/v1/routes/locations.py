"""Authenticated endpoints for an explicitly submitted current device location."""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.config import get_settings
from app.location.reverse_geocoding import (
    NominatimReverseGeocodingProvider,
    ReverseGeocodingProvider,
)
from app.schemas.location import (
    CurrentLocationResponse,
    CurrentLocationUpsert,
    GeocodedPlaceResponse,
    ReverseGeocodedLocationResponse,
    ReverseGeocodeRequest,
)
from app.services.locations import get_current_location, save_current_location

router = APIRouter(prefix="/location")
logger = logging.getLogger(__name__)


@lru_cache
def get_reverse_geocoder() -> ReverseGeocodingProvider:
    return NominatimReverseGeocodingProvider(get_settings())


@router.post(
    "/current",
    response_model=CurrentLocationResponse,
    summary="Store the authenticated user's current device location",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        422: {"description": "Latitude, longitude, or accuracy is invalid"},
    },
)
def save_current_device_location(
    request: CurrentLocationUpsert,
    user: CurrentUser,
    session: DatabaseSession,
    reverse_geocoder: Annotated[ReverseGeocodingProvider, Depends(get_reverse_geocoder)],
    x_request_id: Annotated[str | None, Header()] = None,
) -> CurrentLocationResponse:
    """Replace the last location only when the browser explicitly submits one."""

    settings = get_settings()
    if settings.location_debug:
        logger.info(
            "[LOCATION_DEBUG] source=backend_received latitude=%s longitude=%s "
            "accuracy_meters=%s",
            request.latitude,
            request.longitude,
            request.accuracy_meters,
            extra={"request_id": x_request_id},
        )
    location = save_current_location(
        session,
        user.id,
        request,
        reverse_geocoder,
        user.preferred_language,
        location_debug=settings.location_debug,
        request_id=x_request_id,
    )
    session.commit()
    session.refresh(location)
    if settings.location_debug:
        logger.info(
            "[LOCATION_DEBUG] source=database_retrieved latitude=%s longitude=%s "
            "accuracy_meters=%s",
            location.latitude,
            location.longitude,
            location.accuracy_meters,
            extra={"request_id": x_request_id},
        )
    response = CurrentLocationResponse.model_validate(location)
    if settings.location_debug:
        logger.info(
            "[LOCATION_DEBUG] source=backend_response latitude=%s longitude=%s "
            "location_name=%s",
            response.latitude,
            response.longitude,
            response.location_name,
            extra={"request_id": x_request_id},
        )
    return response


@router.get(
    "/current",
    response_model=CurrentLocationResponse,
    summary="Read the authenticated user's last submitted device location",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        404: {"description": "The user has not submitted a current location"},
    },
)
def read_current_device_location(
    user: CurrentUser, session: DatabaseSession
) -> CurrentLocationResponse:
    location = get_current_location(session, user.id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Current location not found"
        )
    return CurrentLocationResponse.model_validate(location)


@router.get(
    "/search",
    response_model=list[GeocodedPlaceResponse],
    summary="Search for places after an explicit user submission",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        422: {"description": "Search query is too short or too long"},
        503: {"description": "The place search provider is unavailable"},
    },
)
def search_places(
    query: Annotated[str, Query(min_length=3, max_length=120)],
    user: CurrentUser,
    reverse_geocoder: Annotated[ReverseGeocodingProvider, Depends(get_reverse_geocoder)],
) -> list[GeocodedPlaceResponse]:
    normalized_query = query.strip()
    if len(normalized_query) < 3:
        raise HTTPException(
            status_code=422, detail="Search query must contain at least 3 characters"
        )
    places = reverse_geocoder.search_locations(normalized_query, user.preferred_language)
    if places is None:
        raise HTTPException(status_code=503, detail="Location search is temporarily unavailable")
    return [GeocodedPlaceResponse.model_validate(place) for place in places]


@router.post(
    "/reverse",
    response_model=ReverseGeocodedLocationResponse | None,
    summary="Resolve locality details for an explicitly selected map coordinate",
    responses={401: {"description": "Missing, invalid, or expired bearer token"}},
)
def reverse_geocode_selected_place(
    request: ReverseGeocodeRequest,
    user: CurrentUser,
    reverse_geocoder: Annotated[ReverseGeocodingProvider, Depends(get_reverse_geocoder)],
) -> ReverseGeocodedLocationResponse | None:
    place = reverse_geocoder.reverse_geocode(
        request.latitude, request.longitude, user.preferred_language
    )
    return ReverseGeocodedLocationResponse.model_validate(place) if place else None
