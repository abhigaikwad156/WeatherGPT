from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db_session
from app.api.v1.routes import weather as weather_route
from app.domain.models import Farm, User
from app.main import create_app
from app.weather.providers import WeatherProviderError
from app.weather.types import HourlyWeather, NormalizedWeather


def test_farm_weather_provider_failure_returns_service_unavailable(monkeypatch) -> None:
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

        def get_weather(self, _farm: Farm, *, refresh: bool):
            assert refresh is False
            raise WeatherProviderError("provider unavailable")

    monkeypatch.setattr(weather_route, "get_owned_farm", lambda *_args: farm)
    monkeypatch.setattr(weather_route, "WeatherService", FailingWeatherService)
    monkeypatch.setattr(weather_route, "build_provider", lambda _settings: object())
    monkeypatch.setattr(weather_route, "build_cache", lambda _settings: None)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="unused",
        display_name="Farmer",
        is_active=True,
    )
    app.dependency_overrides[get_db_session] = lambda: object()

    with TestClient(app) as client:
        response = client.get(f"/api/v1/farms/{farm.id}/weather")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Current farm weather is unavailable."


def test_farm_weather_response_includes_openweather_current_metrics(monkeypatch) -> None:
    user_id = uuid4()
    farm = Farm(
        id=uuid4(),
        owner_id=user_id,
        name="Owned farm",
        latitude=Decimal("18.5"),
        longitude=Decimal("73.8"),
        location="POINT(73.8 18.5)",
    )
    observed_at = datetime.now(UTC)
    weather = NormalizedWeather(
        farm_id=farm.id,
        provider="openweather",
        fetched_at=observed_at,
        current=HourlyWeather(observed_at, 24, 65, 1.2, 18, "light rain", 1012),
        hourly=(),
        daily=(),
        severe=(),
    )

    class WeatherSession:
        def commit(self) -> None:
            return None

    class StubWeatherService:
        def __init__(self, *_args) -> None:
            pass

        def get_weather(self, _farm: Farm, *, refresh: bool):
            assert refresh is False
            return weather

    monkeypatch.setattr(weather_route, "get_owned_farm", lambda *_args: farm)
    monkeypatch.setattr(weather_route, "WeatherService", StubWeatherService)
    monkeypatch.setattr(weather_route, "build_provider", lambda _settings: object())
    monkeypatch.setattr(weather_route, "build_cache", lambda _settings: None)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="unused",
        display_name="Farmer",
        is_active=True,
    )
    app.dependency_overrides[get_db_session] = WeatherSession

    with TestClient(app) as client:
        response = client.get(f"/api/v1/farms/{farm.id}/weather")

    assert response.status_code == 200
    assert response.json()["current"] == {
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "temperature_celsius": 24.0,
        "humidity_percent": 65.0,
        "rainfall_mm": 1.2,
        "wind_speed_kph": 18.0,
        "condition": "light rain",
        "pressure_hpa": 1012.0,
    }
