from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.domain.models import Farm, User, UserCurrentLocation
from app.main import create_app


class LocationSession:
    """Small in-memory session double for location route behavior tests."""

    def __init__(
        self,
        user: User,
        farm: Farm | None = None,
        current_location: UserCurrentLocation | None = None,
    ) -> None:
        self.user = user
        self.farm = farm
        self.current_location = current_location
        self.commits = 0

    def scalar(self, statement: object) -> Farm | UserCurrentLocation | None:
        entity = statement.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        if entity is Farm:
            return self.farm if self.farm and self.farm.owner_id == self.user.id else None
        if entity is UserCurrentLocation:
            return self.current_location
        return None

    def add(self, item: UserCurrentLocation) -> None:
        self.current_location = item

    def flush(self) -> None:
        if self.current_location is not None:
            self._set_timestamps(self.current_location)

    def commit(self) -> None:
        self.commits += 1
        self.flush()

    def refresh(self, item: Farm | UserCurrentLocation) -> None:
        self._set_timestamps(item)

    @staticmethod
    def _set_timestamps(item: Farm | UserCurrentLocation) -> None:
        now = datetime.now(UTC)
        if item.created_at is None:
            item.created_at = now
        item.updated_at = now


def make_user() -> User:
    return User(
        id=uuid4(),
        email="farmer@example.com",
        password_hash="not-used",
        display_name="Test Farmer",
        preferred_language="mr",
        is_active=True,
    )


def make_farm(owner_id: UUID) -> Farm:
    now = datetime.now(UTC)
    return Farm(
        id=uuid4(),
        owner_id=owner_id,
        name="Test farm",
        latitude=Decimal("18.520400"),
        longitude=Decimal("73.856700"),
        location="POINT(73.856700 18.520400)",
        created_at=now,
        updated_at=now,
    )


def authenticated_client(session: LocationSession) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: session.user
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app)


def test_authenticated_user_can_store_a_current_location() -> None:
    session = LocationSession(make_user())
    with authenticated_client(session) as client:
        response = client.post(
            "/api/v1/location/current",
            json={"latitude": 17.0, "longitude": 74.0, "accuracy_meters": 25.0},
        )

    assert response.status_code == 200
    assert response.json()["latitude"] == "17.0"
    assert response.json()["accuracy_meters"] == "25.0"
    assert session.current_location is not None
    assert session.current_location.user_id == session.user.id
    assert session.commits == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"latitude": 90.1, "longitude": 74.0}, "latitude"),
        ({"latitude": 17.0, "longitude": 180.1}, "longitude"),
        ({"latitude": 17.0, "longitude": 74.0, "accuracy_meters": 0}, "accuracy_meters"),
    ],
)
def test_current_location_rejects_invalid_coordinates_or_accuracy(
    payload: dict[str, float], field: str
) -> None:
    session = LocationSession(make_user())
    with authenticated_client(session) as client:
        response = client.post("/api/v1/location/current", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert any(field in str(detail["loc"]) for detail in response.json()["error"]["details"])


def test_current_location_requires_authentication() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/location/current", json={"latitude": 17.0, "longitude": 74.0}
        )

    assert response.status_code == 401


def test_authenticated_user_can_retrieve_current_location() -> None:
    user = make_user()
    now = datetime.now(UTC)
    current_location = UserCurrentLocation(
        user_id=user.id,
        latitude=Decimal("17.000000"),
        longitude=Decimal("74.000000"),
        accuracy_meters=Decimal("25.00"),
        created_at=now,
        updated_at=now,
    )
    session = LocationSession(user, current_location=current_location)

    with authenticated_client(session) as client:
        response = client.get("/api/v1/location/current")

    assert response.status_code == 200
    assert response.json()["longitude"] == "74.000000"
    assert response.json()["updated_at"]


def test_farmer_can_create_or_update_a_farm_location() -> None:
    user = make_user()
    farm = make_farm(user.id)
    session = LocationSession(user, farm=farm)

    with authenticated_client(session) as client:
        response = client.put(
            f"/api/v1/farms/{farm.id}/location",
            json={
                "latitude": 17.0,
                "longitude": 74.0,
                "accuracy_meters": 15.0,
                "location_name": "Satara, Maharashtra",
            },
        )

    assert response.status_code == 200
    assert response.json()["location_name"] == "Satara, Maharashtra"
    assert farm.latitude == Decimal("17.0")
    assert farm.longitude == Decimal("74.0")
    assert farm.location_accuracy_meters == Decimal("15.0")


def test_farmer_cannot_update_another_users_farm_location() -> None:
    user = make_user()
    farm = make_farm(uuid4())
    session = LocationSession(user, farm=farm)

    with authenticated_client(session) as client:
        response = client.put(
            f"/api/v1/farms/{farm.id}/location",
            json={"latitude": 17.0, "longitude": 74.0},
        )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Farm not found"


def test_farmer_cannot_retrieve_another_users_farm_location() -> None:
    user = make_user()
    farm = make_farm(uuid4())
    session = LocationSession(user, farm=farm)

    with authenticated_client(session) as client:
        response = client.get(f"/api/v1/farms/{farm.id}/location")

    assert response.status_code == 404


def test_farmer_can_copy_current_location_to_an_owned_farm() -> None:
    user = make_user()
    farm = make_farm(user.id)
    farm.location_name = "Old farm location"
    now = datetime.now(UTC)
    current_location = UserCurrentLocation(
        user_id=user.id,
        latitude=Decimal("17.000000"),
        longitude=Decimal("74.000000"),
        accuracy_meters=Decimal("25.00"),
        created_at=now,
        updated_at=now,
    )
    session = LocationSession(user, farm=farm, current_location=current_location)

    with authenticated_client(session) as client:
        response = client.post(f"/api/v1/farms/{farm.id}/location/from-current")

    assert response.status_code == 200
    assert response.json()["latitude"] == "17.000000"
    assert response.json()["accuracy_meters"] == "25.00"
    assert farm.location_name is None


def test_using_current_location_fails_when_no_location_has_been_submitted() -> None:
    user = make_user()
    farm = make_farm(user.id)
    session = LocationSession(user, farm=farm)

    with authenticated_client(session) as client:
        response = client.post(f"/api/v1/farms/{farm.id}/location/from-current")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Current location not found"


def test_farmer_can_retrieve_an_owned_farm_location() -> None:
    user = make_user()
    farm = make_farm(user.id)
    farm.location_name = "User-supplied name"
    session = LocationSession(user, farm=farm)

    with authenticated_client(session) as client:
        response = client.get(f"/api/v1/farms/{farm.id}/location")

    assert response.status_code == 200
    assert response.json()["latitude"] == "18.520400"
    assert response.json()["location_name"] == "User-supplied name"


def test_location_endpoints_are_documented_in_openapi() -> None:
    app = create_app()
    with TestClient(app) as client:
        paths = client.get("/api/v1/openapi.json").json()["paths"]

    assert paths["/api/v1/location/current"]["post"]["summary"]
    assert paths["/api/v1/farms/{farm_id}/location"]["put"]["responses"]["404"]
