"""Provider-independent weather service with caching and persistence."""

from concurrent.futures import Future
from threading import Lock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Farm, WeatherForecast, WeatherObservation
from app.weather.alerts import generate_weather_alerts
from app.weather.cache import WeatherCache
from app.weather.providers import WeatherProvider, WeatherProviderError
from app.weather.types import NormalizedWeather

_IN_FLIGHT_LOCK = Lock()
_IN_FLIGHT_REQUESTS: dict[
    tuple[type[WeatherProvider], UUID, float, float], Future[NormalizedWeather]
] = {}


class WeatherService:
    def __init__(
        self,
        session: Session,
        provider: WeatherProvider,
        cache: WeatherCache | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.cache = cache

    def get_weather(self, farm: Farm, *, refresh: bool = False) -> NormalizedWeather:
        if not refresh and self.cache:
            cached = self.cache.get(farm.id)
            if cached is not None:
                weather = cached
            else:
                weather = self._fetch_and_cache(farm)
        else:
            weather = self._fetch_and_cache(farm)
        generate_weather_alerts(self.session, farm.owner_id, farm, weather)
        return weather

    def _fetch_and_cache(self, farm: Farm) -> NormalizedWeather:
        latitude = float(farm.latitude)
        longitude = float(farm.longitude)
        request_key = (type(self.provider), farm.id, latitude, longitude)
        with _IN_FLIGHT_LOCK:
            request = _IN_FLIGHT_REQUESTS.get(request_key)
            is_request_owner = request is None
            if request is None:
                request = Future()
                _IN_FLIGHT_REQUESTS[request_key] = request
        if not is_request_owner:
            return request.result()

        try:
            try:
                weather = self.provider.fetch(farm.id, latitude, longitude)
            except WeatherProviderError:
                stale = self.cache.get_stale(farm.id) if self.cache else None
                if stale is not None:
                    request.set_result(stale)
                    return stale
                raise
            self._persist(farm, weather)
            if self.cache:
                self.cache.set(weather)
            request.set_result(weather)
            return weather
        except Exception as error:
            request.set_exception(error)
            raise
        finally:
            with _IN_FLIGHT_LOCK:
                if _IN_FLIGHT_REQUESTS.get(request_key) is request:
                    del _IN_FLIGHT_REQUESTS[request_key]

    def _persist(self, farm: Farm, weather: NormalizedWeather) -> None:
        if weather.current:
            current = weather.current
            observation = self.session.scalar(
                select(WeatherObservation).where(
                    WeatherObservation.farm_id == farm.id,
                    WeatherObservation.observed_at == current.observed_at,
                    WeatherObservation.provider == weather.provider,
                )
            )
            if observation is None:
                observation = WeatherObservation(
                    farm_id=farm.id,
                    observed_at=current.observed_at,
                    provider=weather.provider,
                )
                self.session.add(observation)
            observation.condition = current.condition
            observation.temperature_celsius = current.temperature_celsius
            observation.humidity_percent = current.humidity_percent
            observation.rainfall_mm = current.rainfall_mm
            observation.wind_speed_kph = current.wind_speed_kph
        issued_at = weather.fetched_at
        for item in weather.daily:
            self.session.add(
                WeatherForecast(
                    farm_id=farm.id,
                    forecast_for=item.forecast_for,
                    issued_at=issued_at,
                    provider=weather.provider,
                    condition=item.condition,
                    temperature_min_celsius=item.temperature_min_celsius,
                    temperature_max_celsius=item.temperature_max_celsius,
                    precipitation_mm=item.precipitation_mm,
                    rain_probability_percent=item.rain_probability_percent,
                )
            )
        self.session.flush()
