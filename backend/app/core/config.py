from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keep local `uvicorn` runs (started from `backend/`) aligned with Docker,
# which loads the repository-level environment file through docker-compose.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Validated configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "WeatherGPT API"
    app_env: str = Field(default="development", pattern="^(development|test|staging|production)$")
    debug: bool = False
    location_debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]
    database_url: str = "postgresql+psycopg://weathergpt:weathergpt@localhost:5432/weathergpt"
    redis_url: str = "redis://localhost:6379/0"
    weather_provider: str = Field(default="mock", pattern="^(mock|external|open_meteo)$")
    weather_api_url: str | None = None
    weather_api_key: str | None = None
    weather_api_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    weather_api_retries: int = Field(default=2, ge=0, le=5)
    weather_cache_ttl_seconds: int = Field(default=300, gt=0, le=86_400)
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = Field(default="WeatherGPT/1.0", min_length=1)
    nominatim_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; wildcard origins are not allowed"
            )
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=PROJECT_ROOT / ".env")
