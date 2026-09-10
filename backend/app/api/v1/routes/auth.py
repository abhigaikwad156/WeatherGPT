"""Registration and login endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DatabaseSession
from app.core.security import create_access_token
from app.schemas.auth import AuthCredentials, RegistrationRequest, TokenResponse, UserResponse
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegistrationRequest, session: DatabaseSession) -> TokenResponse:
    try:
        user = register_user(session, request)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None
    session.commit()
    session.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
def login(request: AuthCredentials, session: DatabaseSession) -> TokenResponse:
    try:
        user = authenticate_user(session, str(request.email), request.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserResponse.model_validate(user)
    )
