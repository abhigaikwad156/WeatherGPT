"""Location persistence helpers scoped to the existing user and farm models."""

import logging
from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Farm, UserCurrentLocation
from app.location.reverse_geocoding import ReverseGeocodingProvider
from app.schemas.location import CurrentLocationUpsert, FarmLocationUpdate

logger = logging.getLogger(__name__)


def get_current_location(session: Session, user_id: UUID) -> UserCurrentLocation | None:
    return session.scalar(select(UserCurrentLocation).where(UserCurrentLocation.user_id == user_id))


def save_current_location(
    session: Session,
    user_id: UUID,
    request: CurrentLocationUpsert,
    reverse_geocoder: ReverseGeocodingProvider | None = None,
    language: str | None = None,
    *,
    location_debug: bool = False,
    request_id: str | None = None,
) -> UserCurrentLocation:
    location = get_current_location(session, user_id)
    coordinates_changed = location is None or (
        location.latitude != request.latitude or location.longitude != request.longitude
    )
    needs_reverse_lookup = coordinates_changed or (
        location is not None and location.location_name is None
    )
    if location is None:
        location = UserCurrentLocation(user_id=user_id, **request.model_dump())
        session.add(location)
    else:
        location.latitude = request.latitude
        location.longitude = request.longitude
        location.accuracy_meters = request.accuracy_meters
    if coordinates_changed:
        location.location_name = None
        location.city = None
        location.district = None
        location.state = None
        location.country = None
        location.country_code = None
    session.flush()
    if location_debug:
        logger.info(
            "[LOCATION_DEBUG] source=database_stored latitude=%s longitude=%s "
            "accuracy_meters=%s",
            location.latitude,
            location.longitude,
            location.accuracy_meters,
            extra={"request_id": request_id},
        )
    if needs_reverse_lookup and reverse_geocoder is not None:
        if location_debug:
            logger.info(
                "[LOCATION_DEBUG] source=backend_before_reverse_geocode latitude=%s longitude=%s",
                location.latitude,
                location.longitude,
                extra={"request_id": request_id},
            )
        result = reverse_geocoder.reverse_geocode(
            location.latitude, location.longitude, language, request_id=request_id
        )
        if result is not None:
            location.location_name = result.location_name
            location.city = result.city
            location.district = result.district
            location.state = result.state
            location.country = result.country
            location.country_code = result.country_code
    return location


def update_farm_location(farm: Farm, request: FarmLocationUpdate) -> Farm:
    """Update only persisted location fields and keep PostGIS coordinates in sync."""

    farm.latitude = request.latitude
    farm.longitude = request.longitude
    farm.location_accuracy_meters = request.accuracy_meters
    farm.location_name = request.location_name
    farm.location = WKTElement(f"POINT({request.longitude} {request.latitude})", srid=4326)
    return farm


def copy_current_location_to_farm(farm: Farm, location: UserCurrentLocation) -> Farm:
    """Copy a stored device coordinate and its provider-derived display name."""

    farm.latitude = location.latitude
    farm.longitude = location.longitude
    farm.location_accuracy_meters = location.accuracy_meters
    farm.location_name = location.location_name
    farm.location = WKTElement(f"POINT({location.longitude} {location.latitude})", srid=4326)
    return farm
