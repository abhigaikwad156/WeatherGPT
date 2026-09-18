"""Authenticated farm and crop CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.domain.models import Farm, FarmerCrop
from app.schemas.farm import (
    CropCreate,
    CropResponse,
    CropUpdate,
    FarmCreate,
    FarmResponse,
    FarmUpdate,
)
from app.schemas.location import FarmLocationResponse, FarmLocationUpdate
from app.services.locations import (
    copy_current_location_to_farm,
    get_current_location,
    update_farm_location,
)
from app.services.profiles import (
    create_crop,
    create_farm,
    get_owned_crop,
    get_owned_farm,
    update_crop,
    update_farm,
)

router = APIRouter(prefix="/farms")


def _farm_location_response(farm: Farm) -> FarmLocationResponse:
    return FarmLocationResponse(
        latitude=farm.latitude,
        longitude=farm.longitude,
        accuracy_meters=farm.location_accuracy_meters,
        location_name=farm.location_name,
        created_at=farm.created_at,
        updated_at=farm.updated_at,
    )


def _crop_response(crop: FarmerCrop) -> CropResponse:
    return CropResponse(
        id=crop.id,
        farm_id=crop.farm_id,
        name=crop.crop.name,
        variety=crop.variety,
        sowing_date=crop.planted_at,
        growth_stage=crop.growth_stage,
        is_active=crop.is_active,
    )


@router.post("", response_model=FarmResponse, status_code=status.HTTP_201_CREATED)
def create_owned_farm(
    request: FarmCreate, user: CurrentUser, session: DatabaseSession
) -> FarmResponse:
    farm = create_farm(session, user.id, request)
    session.commit()
    session.refresh(farm)
    return FarmResponse.model_validate(farm)


@router.get("", response_model=list[FarmResponse])
def list_owned_farms(user: CurrentUser, session: DatabaseSession) -> list[FarmResponse]:
    farms = session.scalars(select(Farm).where(Farm.owner_id == user.id)).all()
    return [FarmResponse.model_validate(farm) for farm in farms]


@router.put(
    "/{farm_id}/location",
    response_model=FarmLocationResponse,
    summary="Set an owned farm's permanent location",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        404: {"description": "Farm not found or not owned by the authenticated user"},
        422: {"description": "Latitude, longitude, or accuracy is invalid"},
    },
)
def set_owned_farm_location(
    farm_id: UUID, request: FarmLocationUpdate, user: CurrentUser, session: DatabaseSession
) -> FarmLocationResponse:
    """Set coordinates and optional user/provider-supplied location metadata on an owned farm."""

    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    update_farm_location(farm, request)
    session.commit()
    session.refresh(farm)
    return _farm_location_response(farm)


@router.post(
    "/{farm_id}/location/from-current",
    response_model=FarmLocationResponse,
    summary="Use the authenticated user's stored current location for an owned farm",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        404: {
            "description": (
                "Farm is not owned, does not exist, or no current device location was stored"
            )
        },
    },
)
def use_current_location_for_owned_farm(
    farm_id: UUID, user: CurrentUser, session: DatabaseSession
) -> FarmLocationResponse:
    """Copy existing device coordinates; the client does not resend sensitive coordinates."""

    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    location = get_current_location(session, user.id)
    if location is None:
        raise HTTPException(status_code=404, detail="Current location not found")
    copy_current_location_to_farm(farm, location)
    session.commit()
    session.refresh(farm)
    return _farm_location_response(farm)


@router.get(
    "/{farm_id}/location",
    response_model=FarmLocationResponse,
    summary="Read an owned farm's permanent location",
    responses={
        401: {"description": "Missing, invalid, or expired bearer token"},
        404: {"description": "Farm not found or not owned by the authenticated user"},
    },
)
def read_owned_farm_location(
    farm_id: UUID, user: CurrentUser, session: DatabaseSession
) -> FarmLocationResponse:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return _farm_location_response(farm)


@router.get("/{farm_id}", response_model=FarmResponse)
def read_owned_farm(farm_id: UUID, user: CurrentUser, session: DatabaseSession) -> FarmResponse:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return FarmResponse.model_validate(farm)


@router.patch("/{farm_id}", response_model=FarmResponse)
def edit_owned_farm(
    farm_id: UUID, changes: FarmUpdate, user: CurrentUser, session: DatabaseSession
) -> FarmResponse:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    update_farm(farm, changes)
    session.commit()
    session.refresh(farm)
    return FarmResponse.model_validate(farm)


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owned_farm(farm_id: UUID, user: CurrentUser, session: DatabaseSession) -> None:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    session.delete(farm)
    session.commit()


@router.post("/{farm_id}/crops", response_model=CropResponse, status_code=status.HTTP_201_CREATED)
def create_owned_crop(
    farm_id: UUID, request: CropCreate, user: CurrentUser, session: DatabaseSession
) -> CropResponse:
    farm = get_owned_farm(session, user.id, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    crop = create_crop(session, farm, user.id, request)
    session.commit()
    session.refresh(crop)
    return _crop_response(crop)


@router.get("/{farm_id}/crops", response_model=list[CropResponse])
def list_owned_crops(
    farm_id: UUID, user: CurrentUser, session: DatabaseSession
) -> list[CropResponse]:
    if get_owned_farm(session, user.id, farm_id) is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    crops = session.scalars(
        select(FarmerCrop)
        .where(FarmerCrop.farm_id == farm_id, FarmerCrop.farmer_id == user.id)
        .order_by(FarmerCrop.created_at.desc())
    ).all()
    return [_crop_response(crop) for crop in crops]


@router.get("/{farm_id}/crops/{crop_id}", response_model=CropResponse)
def read_owned_crop(
    farm_id: UUID, crop_id: UUID, user: CurrentUser, session: DatabaseSession
) -> CropResponse:
    crop = get_owned_crop(session, user.id, farm_id, crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    return _crop_response(crop)


@router.patch("/{farm_id}/crops/{crop_id}", response_model=CropResponse)
def edit_owned_crop(
    farm_id: UUID,
    crop_id: UUID,
    changes: CropUpdate,
    user: CurrentUser,
    session: DatabaseSession,
) -> CropResponse:
    crop = get_owned_crop(session, user.id, farm_id, crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    update_crop(crop, changes)
    session.commit()
    session.refresh(crop)
    return _crop_response(crop)


@router.delete("/{farm_id}/crops/{crop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owned_crop(
    farm_id: UUID, crop_id: UUID, user: CurrentUser, session: DatabaseSession
) -> None:
    crop = get_owned_crop(session, user.id, farm_id, crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    session.delete(crop)
    session.commit()
