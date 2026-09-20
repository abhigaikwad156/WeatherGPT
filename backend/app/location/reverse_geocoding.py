"""Best-effort reverse geocoding through a replaceable provider interface."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from time import monotonic, sleep
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReverseGeocodedLocation:
    """The small, privacy-conscious address subset WeatherGPT persists."""

    location_name: str | None
    city: str | None
    district: str | None
    state: str | None
    country: str | None
    country_code: str | None


class ReverseGeocodingProvider(Protocol):
    def reverse_geocode(
        self,
        latitude: Decimal,
        longitude: Decimal,
        language: str | None = None,
        *,
        request_id: str | None = None,
    ) -> ReverseGeocodedLocation | None: ...


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def normalize_nominatim_address(payload: object) -> ReverseGeocodedLocation | None:
    """Return only useful locality metadata, never a residential address or a guess."""

    if not isinstance(payload, Mapping) or not isinstance(payload.get("address"), Mapping):
        return None
    address = payload["address"]
    city = next(
        (
            value
            for key in ("city", "town", "municipality", "village", "suburb")
            if (value := _text(address.get(key))) is not None
        ),
        None,
    )
    district = _text(address.get("county")) or _text(address.get("state_district"))
    state = _text(address.get("state"))
    country = _text(address.get("country"))
    country_code = _text(address.get("country_code"))
    if country_code is not None:
        country_code = country_code.upper()

    locality = city or district
    location_name = ", ".join(part for part in (locality, state) if part) or None
    if not any((location_name, city, district, state, country, country_code)):
        return None
    return ReverseGeocodedLocation(location_name, city, district, state, country, country_code)


class NominatimReverseGeocodingProvider:
    """Nominatim adapter with a per-process one-request-per-second safeguard."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        sleep_func: Callable[[float], None] = sleep,
    ) -> None:
        self._base_url = settings.nominatim_base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=settings.nominatim_timeout_seconds)
        self._monotonic_clock = monotonic_clock
        self._sleep = sleep_func
        self._request_lock = Lock()
        self._last_request_at: float | None = None
        self._headers = {"User-Agent": settings.nominatim_user_agent}
        self._location_debug = settings.location_debug

    def reverse_geocode(
        self,
        latitude: Decimal,
        longitude: Decimal,
        language: str | None = None,
        *,
        request_id: str | None = None,
    ) -> ReverseGeocodedLocation | None:
        headers = dict(self._headers)
        if language:
            headers["Accept-Language"] = language
        try:
            if self._location_debug:
                logger.info(
                    "[LOCATION_DEBUG] source=nominatim_request latitude=%s longitude=%s",
                    latitude,
                    longitude,
                    extra={"request_id": request_id},
                )
            with self._request_lock:
                now = self._monotonic_clock()
                if self._last_request_at is not None:
                    wait_seconds = 1 - (now - self._last_request_at)
                    if wait_seconds > 0:
                        self._sleep(wait_seconds)
                self._last_request_at = self._monotonic_clock()
                response = self._client.get(
                    f"{self._base_url}/reverse",
                    params={
                        "format": "jsonv2",
                        "lat": str(latitude),
                        "lon": str(longitude),
                        "addressdetails": 1,
                    },
                    headers=headers,
                )
            if response.status_code in (403, 429) or response.status_code >= 500:
                return None
            response.raise_for_status()
            payload = response.json()
            if self._location_debug and isinstance(payload, Mapping):
                logger.info(
                    "[LOCATION_DEBUG] source=nominatim_response result_latitude=%s "
                    "result_longitude=%s display_name=%s",
                    _text(payload.get("lat")),
                    _text(payload.get("lon")),
                    _text(payload.get("display_name")),
                    extra={"request_id": request_id},
                )
            return normalize_nominatim_address(payload)
        except (httpx.HTTPError, TypeError, ValueError):
            return None
