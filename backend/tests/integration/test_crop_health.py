from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.conversation.gemini import GeminiResponseError
from app.domain.models import Crop, CropHealthReport, Farm, FarmerCrop, User
from app.main import create_app
from app.rag.types import DocumentChunk, RetrievedChunk, SourceMetadata


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


def test_crop_analysis_uses_retrieved_sources_and_returns_guidance(monkeypatch):
    from app.api.v1.routes import crop_health

    client, _, session = setup_client()
    chunk = RetrievedChunk(
        DocumentChunk(
            document_id=uuid4(),
            chunk_id=uuid4(),
            text="Leaf spots may result from several causes. Remove affected material.",
            metadata=SourceMetadata(
                source_id="guide-1",
                title="Tomato disease guide",
                publisher="Agricultural Extension",
                source_uri="https://example.test/tomato-guide",
                trusted=True,
            ),
            ordinal=0,
        ),
        score=0.9,
    )

    class Retriever:
        def retrieve(self, query, *, limit):
            assert "Tomato" in query
            assert "leaf spots" in query
            assert "7 days" in query
            assert limit == 5
            return [chunk]

    class Gemini:
        def __init__(self, _settings):
            pass

        def respond(self, question, language, context):
            assert "not a confirmed diagnosis" in question
            assert "soil_type" in context
            assert "guide-1" in context
            assert language == "mr"
            return (
                "Possible causes: leaf spot disease [guide-1]. "
                "Remove affected material [guide-1]."
            )

    monkeypatch.setattr(crop_health, "_retrieval_service", lambda _session: Retriever())
    monkeypatch.setattr(crop_health, "GeminiChatService", Gemini)

    response = client.post("/api/v1/crop-health/analyze", json=valid_payload(session))

    assert response.status_code == 200
    assert response.json() == {
        "status": "analysis",
        "analysis": (
            "Possible causes: leaf spot disease [guide-1]. "
            "Remove affected material [guide-1]."
        ),
        "follow_up": None,
        "sources": [
            {
                "source_id": "guide-1",
                "title": "Tomato disease guide",
                "publisher": "Agricultural Extension",
                "source_uri": "https://example.test/tomato-guide",
            }
        ],
    }
    assert session.reports == []


def test_crop_analysis_requests_more_information_when_no_sources(monkeypatch):
    from app.api.v1.routes import crop_health

    client, _, session = setup_client()

    class Retriever:
        def retrieve(self, _query, *, limit):
            assert limit == 5
            return []

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("AI should not be called without retrieved sources")

    monkeypatch.setattr(crop_health, "_retrieval_service", lambda _session: Retriever())
    monkeypatch.setattr(crop_health, "GeminiChatService", fail_if_called)

    response = client.post("/api/v1/crop-health/analyze", json=valid_payload(session))

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_information"
    assert response.json()["analysis"] is None
    assert "describe what you observe" in response.json()["follow_up"]
    assert response.json()["sources"] == []


def test_crop_analysis_reports_ai_service_failure(monkeypatch):
    from app.api.v1.routes import crop_health

    client, _, session = setup_client()

    class Retriever:
        def retrieve(self, _query, *, limit):
            return [
                RetrievedChunk(
                    DocumentChunk(
                        document_id=uuid4(),
                        chunk_id=uuid4(),
                        text="A relevant crop health reference.",
                        metadata=SourceMetadata(
                            source_id="guide-1",
                            title="Crop guide",
                            publisher="Extension",
                        ),
                        ordinal=0,
                    ),
                    score=0.8,
                )
            ]

    class Gemini:
        def __init__(self, _settings):
            pass

        def respond(self, *_args):
            raise GeminiResponseError("provider unavailable")

    monkeypatch.setattr(crop_health, "_retrieval_service", lambda _session: Retriever())
    monkeypatch.setattr(crop_health, "GeminiChatService", Gemini)

    response = client.post("/api/v1/crop-health/analyze", json=valid_payload(session))

    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Crop health analysis is temporarily unavailable. Please try again."
    )


def test_crop_analysis_reports_retrieval_service_failure(monkeypatch):
    from app.api.v1.routes import crop_health

    client, _, session = setup_client()

    class Retriever:
        def retrieve(self, *_args, **_kwargs):
            raise RuntimeError("retrieval unavailable")

    monkeypatch.setattr(crop_health, "_retrieval_service", lambda _session: Retriever())

    response = client.post("/api/v1/crop-health/analyze", json=valid_payload(session))

    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Crop health analysis is temporarily unavailable. Please try again."
    )


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
