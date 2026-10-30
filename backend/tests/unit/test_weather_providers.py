import logging
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.weather.providers import (
    ExternalWeatherProvider,
    MockWeatherProvider,
    OpenWeatherProvider,
    WeatherProviderError,
)


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


def test_openweather_provider_maps_current_and_five_day_forecast(caplog) -> None:
    caplog.set_level(logging.INFO, logger="httpx")
    farm_id = uuid4()
    now = datetime(2026, 1, 1, 21, tzinfo=UTC)
    timestamp = now.timestamp()
    requests: list[httpx.Request] = []

    def weather_response(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/weather"):
            return httpx.Response(
                200,
                json={
                    "dt": timestamp,
                    "main": {"temp": 24, "humidity": 65},
                    "rain": {"1h": 1.2},
                    "wind": {"speed": 5},
                    "weather": [{"description": "light rain"}],
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "city": {"timezone": 19_800},
                "list": [
                    {
                        "dt": timestamp + 3600,
                        "main": {"temp": 20, "temp_min": 12, "temp_max": 22, "humidity": 70},
                        "rain": {"3h": 0.5},
                        "wind": {"speed": 2},
                        "pop": 0.25,
                        "weather": [{"description": "cloudy"}],
                    },
                    {
                        "dt": timestamp + 4 * 3600,
                        "main": {"temp": 18, "temp_min": 14, "temp_max": 24, "humidity": 75},
                        "rain": {"3h": 1},
                        "wind": {"speed": 3},
                        "pop": 0.75,
                        "weather": [{"description": "cloudy"}],
                    },
                    {
                        "dt": timestamp + 28 * 3600,
                        "main": {"temp": 19, "temp_min": 15, "temp_max": 25, "humidity": 72},
                        "weather": [{"description": "clear sky"}],
                    },
                ],
            },
            request=request,
        )

    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="openweather",
        openweather_api_key="test-key",
    )
    client = httpx.Client(transport=httpx.MockTransport(weather_response))

    weather = OpenWeatherProvider(settings, client).fetch(farm_id, 18.52, 73.85)

    assert weather.provider == "openweather"
    assert weather.current is not None
    assert weather.current.temperature_celsius == 24
    assert weather.current.humidity_percent == 65
    assert weather.current.rainfall_mm == 1.2
    assert weather.current.wind_speed_kph == 18
    assert weather.current.condition == "light rain"
    assert len(weather.hourly) == 3
    assert weather.hourly[0].wind_speed_kph == 7.2
    assert len(weather.daily) == 2
    assert weather.daily[0].forecast_for.isoformat() == "2026-01-02T00:00:00+05:30"
    assert weather.daily[0].temperature_min_celsius == 12
    assert weather.daily[0].temperature_max_celsius == 24
    assert weather.daily[0].precipitation_mm == 1.5
    assert weather.daily[0].rain_probability_percent == 75
    assert weather.daily[0].condition == "cloudy"
    assert weather.daily[1].rain_probability_percent is None
    assert "test-key" not in caplog.text
    assert len(requests) == 2
    for request, endpoint in zip(
        requests,
        ("/data/2.5/weather", "/data/2.5/forecast"),
        strict=True,
    ):
        assert request.url.host == "api.openweathermap.org"
        assert request.url.path == endpoint
        assert request.url.params["appid"] == "test-key"
        assert request.url.params["units"] == "metric"
        assert request.url.params["lat"] == "18.52"
        assert request.url.params["lon"] == "73.85"


def test_openweather_provider_does_not_retry_rate_limits() -> None:
    requests: list[httpx.Request] = []

    def rate_limited(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, request=request)

    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="openweather",
        openweather_api_key="test-key",
        weather_api_retries=2,
    )
    client = httpx.Client(transport=httpx.MockTransport(rate_limited))

    with pytest.raises(WeatherProviderError, match="OpenWeather request failed"):
        OpenWeatherProvider(settings, client).fetch(uuid4(), 18.52, 73.85)

    assert len(requests) == 1


def test_openweather_provider_retries_timeouts_then_reports_provider_error() -> None:
    requests = 0

    def timed_out(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise httpx.ReadTimeout("timed out")

    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="openweather",
        openweather_api_key="test-key",
        weather_api_retries=1,
    )
    client = httpx.Client(transport=httpx.MockTransport(timed_out))

    with pytest.raises(WeatherProviderError, match="OpenWeather request failed"):
        OpenWeatherProvider(settings, client).fetch(uuid4(), 18.52, 73.85)

    assert requests == 2


def test_openweather_provider_requires_api_key() -> None:
    settings = Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        weather_provider="openweather",
    )

    with pytest.raises(WeatherProviderError, match="OPENWEATHER_API_KEY"):
        OpenWeatherProvider(settings)
