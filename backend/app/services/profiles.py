"""Farmer, farm, and crop profile use cases."""

from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Crop, Farm, FarmerCrop, User
from app.schemas.farm import CropCreate, CropUpdate, FarmCreate, FarmUpdate
from app.schemas.profile import FarmerProfileUpdate


def update_profile(user: User, changes: FarmerProfileUpdate) -> User:
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    return user


def get_owned_farm(session: Session, user_id: UUID, farm_id: UUID) -> Farm | None:
    return session.scalar(select(Farm).where(Farm.id == farm_id, Farm.owner_id == user_id))


def create_farm(session: Session, user_id: UUID, request: FarmCreate) -> Farm:
    farm = Farm(
        owner_id=user_id,
        location=WKTElement(f"POINT({request.longitude} {request.latitude})", srid=4326),
        **request.model_dump(),
    )
    session.add(farm)
    session.flush()
    return farm


def update_farm(farm: Farm, changes: FarmUpdate) -> Farm:
    values = changes.model_dump(exclude_unset=True)
    for field, value in values.items():
        setattr(farm, field, value)
    if "latitude" in values or "longitude" in values:
        farm.location = WKTElement(f"POINT({farm.longitude} {farm.latitude})", srid=4326)
    return farm


def create_crop(session: Session, farm: Farm, user_id: UUID, request: CropCreate) -> FarmerCrop:
    crop = session.scalar(select(Crop).where(Crop.name == request.name))
    if crop is None:
        crop = Crop(name=request.name)
        session.add(crop)
        session.flush()
    farmer_crop = FarmerCrop(
        farmer_id=user_id,
        farm_id=farm.id,
        crop_id=crop.id,
        variety=request.variety,
        planted_at=request.sowing_date,
        growth_stage=request.growth_stage,
    )
    session.add(farmer_crop)
    session.flush()
    farmer_crop.crop = crop
    return farmer_crop


def get_owned_crop(
    session: Session, user_id: UUID, farm_id: UUID, crop_id: UUID
) -> FarmerCrop | None:
    return session.scalar(
        select(FarmerCrop).where(
            FarmerCrop.id == crop_id,
            FarmerCrop.farmer_id == user_id,
            FarmerCrop.farm_id == farm_id,
        )
    )


def update_crop(crop: FarmerCrop, changes: CropUpdate) -> FarmerCrop:
    values = changes.model_dump(exclude_unset=True)
    if "name" in values:
        crop.crop.name = values.pop("name")
    if "sowing_date" in values:
        values["planted_at"] = values.pop("sowing_date")
    for field, value in values.items():
        setattr(crop, field, value)
    return crop
