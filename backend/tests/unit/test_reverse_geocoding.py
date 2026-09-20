from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.location.reverse_geocoding import NominatimReverseGeocodingProvider


def settings() -> Settings:
    return Settings(
        jwt_secret_key="test-only-secret-key-change-me-32chars",
        nominatim_base_url="https://nominatim.test",
        nominatim_user_agent="WeatherGPT-tests/1.0 (test contact)",
    )


@pytest.mark.parametrize(
    ("address", "expected_name", "expected_city"),
    [
        (
            {
                "city": "Example City",
                "county": "Example District",
                "state": "Maharashtra",
                "country": "India",
                "country_code": "in",
            },
            "Example City, Maharashtra",
            "Example City",
        ),
        (
            {"town": "Example Town", "state": "Maharashtra", "country": "India"},
            "Example Town, Maharashtra",
            "Example Town",
        ),
        (
            {"village": "Example Village", "state": "Maharashtra", "country": "India"},
            "Example Village, Maharashtra",
            "Example Village",
        ),
        (
            {"state": "Maharashtra", "country": "India"},
            "Maharashtra",
            None,
        ),
    ],
)
def test_nominatim_normalizes_available_address_fields(
    address: dict[str, str], expected_name: str, expected_city: str | None
) -> None:
    captured: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "lat": "19.9975",
                "lon": "73.7898",
                "display_name": "Example result",
                "address": address,
            },
            request=request,
        )

    provider = NominatimReverseGeocodingProvider(
        settings(), httpx.Client(transport=httpx.MockTransport(transport))
    )

    result = provider.reverse_geocode(Decimal("19.9975"), Decimal("73.7898"), "mr")

    assert result is not None
    assert result.location_name == expected_name
    assert result.city == expected_city
    assert result.state == "Maharashtra"
    assert result.country == "India"
    assert captured[0].url.path == "/reverse"
    assert dict(captured[0].url.params) == {
        "format": "jsonv2",
        "lat": "19.9975",
        "lon": "73.7898",
        "addressdetails": "1",
    }
    assert captured[0].headers["user-agent"] == "WeatherGPT-tests/1.0 (test contact)"
    assert captured[0].headers["accept-language"] == "mr"


@pytest.mark.parametrize(
    "response",
    [
        lambda request: httpx.Response(429, request=request),
        lambda request: httpx.Response(200, content=b"not-json", request=request),
    ],
)
def test_nominatim_failures_are_graceful(response: object) -> None:
    client = httpx.Client(transport=httpx.MockTransport(response))  # type: ignore[arg-type]
    provider = NominatimReverseGeocodingProvider(settings(), client)

    assert provider.reverse_geocode(Decimal("19.9975"), Decimal("73.7898")) is None


def test_nominatim_timeout_is_graceful() -> None:
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    provider = NominatimReverseGeocodingProvider(
        settings(), httpx.Client(transport=httpx.MockTransport(timeout))
    )

    assert provider.reverse_geocode(Decimal("19.9975"), Decimal("73.7898")) is None
