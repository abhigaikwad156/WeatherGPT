from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.weather.providers import ExternalWeatherProvider, MockWeatherProvider, WeatherProviderError


def test_mock_provider_returns_normalized_weather() -> None:
    weather = MockWeatherProvider().fetch(uuid4(), 18.52, 73.85)

    assert weather.provider == "mock"
    assert weather.current is not None
    assert weather.current.temperature_celsius == 27.0
    assert weather.daily[0].rain_probability_percent == 25.0


def test_external_provider_normalizes_payload() -> None:
    farm_id = uuid4()
    payload = {
        "current": {
            "observed_at": "2026-09-10T08:00:00+00:00",
            "temperature_celsius": 28,
            "humidity_percent": 70,
            "rainfall_mm": 0,
            "wind_speed_kph": 12,
            "condition": "clear",
        },
        "hourly": [],
        "daily": [
            {
                "forecast_for": "2026-09-11T00:00:00+00:00",
                "temperature_min_celsius": 21,
                "temperature_max_celsius": 30,
                "precipitation_mm": 2,
                "rain_probability_percent": 30,
                "condition": "cloudy",
            }
        ],
        "severe": [],
    }
    request = httpx.Request("GET", "https://weather.test")
    response = httpx.Response(200, json=payload, request=request)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: response))
    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="external",
        weather_api_url="https://weather.test",
        weather_api_key="provider-key",
    )

    weather = ExternalWeatherProvider(settings, client).fetch(farm_id, 18.52, 73.85)

    assert weather.provider == "external"
    assert weather.current is not None
    assert weather.current.condition == "clear"
    assert weather.daily[0].temperature_max_celsius == 30.0


def test_external_provider_retries_then_reports_provider_error() -> None:
    calls = 0

    def failing_transport(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timed out")

    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="external",
        weather_api_url="https://weather.test",
        weather_api_key="provider-key",
        weather_api_retries=2,
    )
    client = httpx.Client(transport=httpx.MockTransport(failing_transport))

    with pytest.raises(WeatherProviderError, match="request failed"):
        ExternalWeatherProvider(settings, client).fetch(uuid4(), 18.52, 73.85)

    assert calls == 3


def test_external_provider_requires_configuration() -> None:
    settings = Settings(jwt_secret_key="test-only-secret-key-change-me-32chars")

    with pytest.raises(WeatherProviderError, match="WEATHER_API_URL"):
        ExternalWeatherProvider(settings)
