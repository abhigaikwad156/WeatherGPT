from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.domain.models import AlertSeverity, User, WeatherAlert
from app.main import create_app


class AlertResult:
    def __init__(self, alerts: list[WeatherAlert]) -> None:
        self.alerts = alerts

    def all(self) -> list[WeatherAlert]:
        return self.alerts


class AlertSession:
    def __init__(self, alerts: list[WeatherAlert]) -> None:
        self.alerts = alerts
        self.statement: object | None = None

    def scalars(self, statement: object) -> AlertResult:
        self.statement = statement
        return AlertResult(self.alerts)


def test_weather_alerts_returns_active_alerts_for_authenticated_user() -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    alert = WeatherAlert(
        id=uuid4(),
        user_id=user_id,
        farm_id=uuid4(),
        alert_type="existing",
        severity=AlertSeverity.HIGH,
        title="Persisted alert",
        body="Alert content from an existing weather rule.",
        starts_at=now,
        ends_at=None,
        acknowledged_at=None,
    )
    session = AlertSession([alert])
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="not-used",
        display_name="Farmer",
        is_active=True,
    )
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app) as client:
        response = client.get("/api/v1/weather-alerts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(alert.id),
            "title": "Persisted alert",
            "body": "Alert content from an existing weather rule.",
            "severity": "high",
            "startsAt": now.isoformat().replace("+00:00", "Z"),
        }
    ]
    statement = str(session.statement)
    assert "weather_alerts.user_id" in statement
    assert "weather_alerts.starts_at" in statement
    assert "weather_alerts.acknowledged_at" in statement
    assert "weather_alerts.ends_at" in statement


def test_weather_alerts_requires_authentication() -> None:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: AlertSession([])

    with TestClient(app) as client:
        response = client.get("/api/v1/weather-alerts")

    assert response.status_code == 401
