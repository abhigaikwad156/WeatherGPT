"""Authentication use cases backed by the user repository."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.domain.models import User
from app.schemas.auth import RegistrationRequest


class EmailAlreadyRegisteredError(Exception):
    """Raised when a registration email is already in use."""


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid."""


def register_user(session: Session, request: RegistrationRequest) -> User:
    normalized_email = str(request.email).lower()
    existing = session.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=normalized_email,
        password_hash=hash_password(request.password),
        display_name=request.display_name,
        preferred_language="mr",
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyRegisteredError from exc
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    return user
