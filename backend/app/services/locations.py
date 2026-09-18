"""Location persistence helpers scoped to the existing user and farm models."""

from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Farm, UserCurrentLocation
from app.schemas.location import CurrentLocationUpsert, FarmLocationUpdate


def get_current_location(session: Session, user_id: UUID) -> UserCurrentLocation | None:
    return session.scalar(select(UserCurrentLocation).where(UserCurrentLocation.user_id == user_id))


def save_current_location(
    session: Session, user_id: UUID, request: CurrentLocationUpsert
) -> UserCurrentLocation:
    location = get_current_location(session, user_id)
    if location is None:
        location = UserCurrentLocation(user_id=user_id, **request.model_dump())
        session.add(location)
    else:
        location.latitude = request.latitude
        location.longitude = request.longitude
        location.accuracy_meters = request.accuracy_meters
    session.flush()
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
    """Copy a stored device coordinate without retaining a stale location name."""

    farm.latitude = location.latitude
    farm.longitude = location.longitude
    farm.location_accuracy_meters = location.accuracy_meters
    farm.location_name = None
    farm.location = WKTElement(f"POINT({location.longitude} {location.latitude})", srid=4326)
    return farm
