from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.api.v1.routes import dashboard as dashboard_route
from app.domain.models import Farm, User
from app.main import create_app
from app.weather.providers import WeatherProviderError


class DashboardSession:
    def __init__(self, farm: Farm) -> None:
        self.farm = farm

    def scalar(self, _statement: object) -> Farm:
        return self.farm


def test_dashboard_weather_provider_failure_returns_service_unavailable(monkeypatch) -> None:
    user_id = uuid4()
    farm = Farm(
        id=uuid4(),
        owner_id=user_id,
        name="Owned farm",
        latitude=Decimal("18.5"),
        longitude=Decimal("73.8"),
        location="POINT(73.8 18.5)",
    )

    class FailingWeatherService:
        def __init__(self, *_args) -> None:
            pass

        def get_weather(self, _farm: Farm):
            raise WeatherProviderError("provider unavailable")

    monkeypatch.setattr(dashboard_route, "WeatherService", FailingWeatherService)
    monkeypatch.setattr(dashboard_route, "build_provider", lambda _settings: object())
    monkeypatch.setattr(dashboard_route, "build_cache", lambda _settings: None)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="unused",
        display_name="Farmer",
        is_active=True,
    )
    app.dependency_overrides[get_db_session] = lambda: DashboardSession(farm)

    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Current farm weather is unavailable; dashboard data was not generated."
    )
