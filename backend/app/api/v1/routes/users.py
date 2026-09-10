"""Authenticated user endpoints."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users")


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
