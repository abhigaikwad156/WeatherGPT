from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.core.security import hash_password
from app.domain.models import User
from app.main import create_app


class FakeSession:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.added_user: User | None = None

    def scalar(self, _statement: object) -> User | None:
        return self.user

    def add(self, user: User) -> None:
        self.added_user = user
        self.user = user

    def flush(self) -> None:
        if self.added_user is not None:
            self.added_user.id = uuid4()

    def commit(self) -> None:
        return None

    def refresh(self, _user: User) -> None:
        return None


def test_register_returns_access_token_without_plaintext_password() -> None:
    session = FakeSession()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "farmer@example.com",
                "password": "secure-pass-123",
                "display_name": "Ramesh Kumar",
            },
        )

    assert response.status_code == 201
    assert response.json()["token_type"] == "bearer"
    assert response.json()["user"]["email"] == "farmer@example.com"
    assert session.added_user is not None
    assert session.added_user.password_hash != "secure-pass-123"


def test_login_and_current_user_endpoint_require_valid_bearer_token() -> None:
    user = User(
        id=uuid4(),
        email="farmer@example.com",
        password_hash=hash_password("secure-pass-123"),
        display_name="Ramesh Kumar",
        preferred_language="mr",
        is_active=True,
    )
    session = FakeSession(user)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/users/me")
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "farmer@example.com", "password": "secure-pass-123"},
        )
        authorized = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert unauthorized.status_code == 401
    assert login.status_code == 200
    assert authorized.status_code == 200
    assert authorized.json()["display_name"] == "Ramesh Kumar"


def test_login_rejects_invalid_credentials() -> None:
    session = FakeSession(
        User(
            id=uuid4(),
            email="farmer@example.com",
            password_hash=hash_password("secure-pass-123"),
            display_name="Ramesh Kumar",
            preferred_language="mr",
            is_active=True,
        )
    )
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "farmer@example.com", "password": "wrong-pass-123"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"
