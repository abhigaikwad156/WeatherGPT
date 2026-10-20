from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.domain.models import Crop, CropHealthReport, Farm, FarmerCrop, User
from app.main import create_app


class CropHealthSession:
    def __init__(self, user_id):
        self.user_id = user_id
        farm = Farm(
            id=uuid4(),
            owner_id=user_id,
            name="My farm",
            latitude=0,
            longitude=0,
            location=None,
        )
        crop = Crop(id=uuid4(), name="Tomato")
        self.association = FarmerCrop(
            id=uuid4(),
            farm_id=farm.id,
            farmer_id=user_id,
            crop_id=crop.id,
            farm=farm,
            crop=crop,
        )
        self.reports = []
        self.committed = False

    def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is FarmerCrop:
            sql = str(statement)
            assert "farms.owner_id" in sql
            assert "farmer_crops.farm_id" in sql
            assert "farmer_crops.farmer_id" in sql
            params = statement.compile().params.values()
            if (
                self.association.id in params
                and self.association.farm_id in params
                and self.user_id in params
                and self.association.farmer_id == self.user_id
                and self.association.farm.owner_id == self.user_id
            ):
                return self.association
            return None
        params = statement.compile().params.values()
        report_id = next(
            (
                value
                for value in self.reports
                if value.id in params
                and self.user_id in params
                and value.owner_id == self.user_id
            ),
            None,
        )
        return report_id

    def scalars(self, _statement):
        reports = sorted(
            (report for report in self.reports if report.owner_id == self.user_id),
            key=lambda report: report.created_at,
            reverse=True,
        )
        offset = (
            _statement._offset_clause.value if _statement._offset_clause is not None else 0
        )
        limit = (
            _statement._limit_clause.value if _statement._limit_clause is not None else None
        )
        reports = reports[offset : offset + limit if limit is not None else None]
        return SimpleNamespace(all=lambda: reports)

    def add(self, report):
        report.id = uuid4()
        report.created_at = datetime.now(UTC)
        self.reports.append(report)

    def commit(self):
        self.committed = True

    def refresh(self, _report):
        return None


def setup_client():
    user = User(
        id=uuid4(),
        email="farmer@example.com",
        password_hash="not-used",
        display_name="Ramesh Kumar",
        is_active=True,
    )
    session = CropHealthSession(user.id)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app), user, session


def valid_payload(session):
    return {
        "farm_id": str(session.association.farm_id),
        "crop_id": str(session.association.id),
        "symptoms": ["leaf_spots", "yellowing"],
        "duration_days": 7,
        "notes": "Observed on lower leaves",
    }


def test_authenticated_farmer_can_create_report():
    client, user, session = setup_client()
    response = client.post("/api/crop-health/reports", json=valid_payload(session))

    assert response.status_code == 201
    assert response.json()["owner_id"] == str(user.id)
    assert response.json()["farm_name"] == "My farm"
    assert response.json()["crop_name"] == "Tomato"
    assert response.json()["symptoms"] == ["leaf_spots", "yellowing"]
    assert session.committed


def test_report_rejects_unknown_symptoms_and_invalid_duration():
    client, _, session = setup_client()
    payload = valid_payload(session)

    unknown = client.post(
        "/api/crop-health/reports",
        json={**payload, "symptoms": ["made_up_symptom"]},
    )
    missing_symptoms = client.post(
        "/api/crop-health/reports",
        json={**payload, "symptoms": []},
    )
    duration = client.post(
        "/api/crop-health/reports",
        json={**payload, "duration_days": 366},
    )
    forged_owner = client.post(
        "/api/crop-health/reports",
        json={**payload, "owner_id": str(uuid4())},
    )

    assert unknown.status_code == 422
    assert missing_symptoms.status_code == 422
    assert duration.status_code == 422
    assert forged_owner.status_code == 422


def test_report_requires_authentication():
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: CropHealthSession(uuid4())

    with TestClient(app) as client:
        response = client.get("/api/crop-health/reports")

    assert response.status_code == 401


def test_report_requires_owned_farm_and_associated_crop():
    client, _, session = setup_client()
    session.association.farmer_id = uuid4()

    response = client.post("/api/crop-health/reports", json=valid_payload(session))

    assert response.status_code == 404


def test_report_rejects_crop_from_another_farm():
    client, _, session = setup_client()
    payload = {**valid_payload(session), "farm_id": str(uuid4())}

    response = client.post("/api/crop-health/reports", json=payload)

    assert response.status_code == 404


def test_report_list_is_scoped_to_authenticated_owner():
    client, user, session = setup_client()
    first = client.post("/api/crop-health/reports", json=valid_payload(session))
    second = client.post(
        "/api/crop-health/reports",
        json={**valid_payload(session), "symptoms": ["wilting"], "duration_days": 3},
    )
    session.reports.append(
        CropHealthReport(
            id=uuid4(),
            owner_id=uuid4(),
            farm_id=uuid4(),
            crop_id=uuid4(),
            symptoms=["root_rot"],
            duration_days=5,
            created_at=datetime.now(UTC),
        )
    )

    response = client.get("/api/crop-health/reports?limit=1")

    assert first.status_code == 201
    assert second.status_code == 201
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == second.json()["id"]
    assert all(report["owner_id"] == str(user.id) for report in response.json())


def test_report_is_not_visible_to_another_user():
    client, _, session = setup_client()
    report = client.post("/api/crop-health/reports", json=valid_payload(session))
    report_id = report.json()["id"]
    own_report = client.get(f"/api/crop-health/reports/{report_id}")
    assert own_report.status_code == 200

    other_user = User(
        id=uuid4(),
        email="other@example.com",
        password_hash="not-used",
        display_name="Another farmer",
        is_active=True,
    )
    client.app.dependency_overrides[get_current_user] = lambda: other_user

    response = client.get(f"/api/crop-health/reports/{report_id}")

    assert response.status_code == 404
