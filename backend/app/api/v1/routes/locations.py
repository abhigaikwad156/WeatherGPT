"""Authenticated endpoints for an explicitly submitted current device location."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.schemas.location import CurrentLocationResponse, CurrentLocationUpsert
from app.services.locations import get_current_location, save_current_location

router = APIRouter(prefix="/location")


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
    request: CurrentLocationUpsert, user: CurrentUser, session: DatabaseSession
) -> CurrentLocationResponse:
    """Replace the last location only when the browser explicitly submits one."""

    location = save_current_location(session, user.id, request)
    session.commit()
    session.refresh(location)
    return CurrentLocationResponse.model_validate(location)


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
