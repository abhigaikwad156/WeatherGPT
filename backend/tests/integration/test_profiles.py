from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.domain.models import User
from app.main import create_app


class ProfileSession:
    def commit(self) -> None:
        return None

    def refresh(self, _user: User) -> None:
        return None

    def scalar(self, _statement: object) -> None:
        return None


def test_farmer_can_update_profile_preferences() -> None:
    user = User(
        id=uuid4(),
        email="farmer@example.com",
        password_hash="not-used",
        display_name="Ramesh Kumar",
        preferred_language="mr",
        preferred_units="metric",
        is_active=True,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = ProfileSession

    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/users/me/profile",
            json={"preferred_language": "hi", "location": "Pune", "preferred_units": "imperial"},
        )

    assert response.status_code == 200
    assert response.json()["preferred_language"] == "hi"
    assert response.json()["location"] == "Pune"
    assert user.preferred_units == "imperial"


def test_farmer_cannot_read_a_farm_they_do_not_own() -> None:
    user = User(
        id=uuid4(),
        email="farmer@example.com",
        password_hash="not-used",
        display_name="Ramesh Kumar",
        is_active=True,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = ProfileSession

    with TestClient(app) as client:
        response = client.get(f"/api/v1/farms/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Farm not found"
