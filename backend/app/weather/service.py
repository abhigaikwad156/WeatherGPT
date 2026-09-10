"""Provider-independent weather service with caching and persistence."""

from sqlalchemy.orm import Session

from app.domain.models import Farm, WeatherForecast, WeatherObservation
from app.weather.cache import WeatherCache
from app.weather.providers import WeatherProvider
from app.weather.types import NormalizedWeather


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
                return cached
        weather = self.provider.fetch(farm.id, float(farm.latitude), float(farm.longitude))
        self._persist(farm, weather)
        if self.cache:
            self.cache.set(weather)
        return weather

    def _persist(self, farm: Farm, weather: NormalizedWeather) -> None:
        if weather.current:
            current = weather.current
            self.session.add(
                WeatherObservation(
                    farm_id=farm.id,
                    observed_at=current.observed_at,
                    provider=weather.provider,
                    condition=current.condition,
                    temperature_celsius=current.temperature_celsius,
                    humidity_percent=current.humidity_percent,
                    rainfall_mm=current.rainfall_mm,
                    wind_speed_kph=current.wind_speed_kph,
                )
            )
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
