"""Authenticated farmer profile endpoints."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DatabaseSession
from app.schemas.profile import FarmerProfileResponse, FarmerProfileUpdate
from app.services.profiles import update_profile

router = APIRouter(prefix="/users")


@router.get("/me/profile", response_model=FarmerProfileResponse)
def read_profile(user: CurrentUser) -> FarmerProfileResponse:
    return FarmerProfileResponse.model_validate(user, from_attributes=True)


@router.patch("/me/profile", response_model=FarmerProfileResponse)
def edit_profile(
    changes: FarmerProfileUpdate, user: CurrentUser, session: DatabaseSession
) -> FarmerProfileResponse:
    update_profile(user, changes)
    session.commit()
    session.refresh(user)
    return FarmerProfileResponse.model_validate(user, from_attributes=True)
