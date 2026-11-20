from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None
    weather_provider: str = Field(default="mock", pattern="^(mock|external|openweather)$")
    weather_api_url: str | None = None
    weather_api_key: str | None = None
    openweather_api_key: str | None = None
    weather_api_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    weather_api_retries: int = Field(default=2, ge=0, le=5)
    weather_cache_ttl_seconds: int = Field(default=300, gt=0, le=86_400)
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = Field(default="WeatherGPT/1.0", min_length=1)
    nominatim_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    rag_embedding_model: str = "gemini-embedding-001"
    rag_embedding_dimension: int = Field(default=1536, ge=1)
    embedding_provider: Literal["gemini", "alibaba", "cohere"] = "gemini"
    dashscope_api_key: str | None = None
    dashscope_base_url: str | None = None
    cohere_api_key: str | None = None
    rag_minimum_score: float = Field(default=0.55, ge=-1.0, le=1.0)
    rag_trusted_publishers: list[str] = Field(default_factory=list)
    rag_trusted_domains: list[str] = Field(
        default_factory=lambda: [
            "nitiforstates.gov.in",
            "www.nitiforstates.gov.in",
            "mpkv.ac.in",
            "icar.org.in",
            "www.icar.org.in",
            "icar.gov.in",
            "www.icar.gov.in",
            "agritech.tnau.ac.in",
            "www.agritech.tnau.ac.in",
        ]
    )
    rag_web_max_download_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    agricultural_thresholds_path: Path | None = None

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; wildcard origins are not allowed"
            )
        return origins

    @field_validator("database_url")
    @classmethod
    def use_installed_postgres_driver(cls, value: str) -> str:
        for scheme in ("postgres://", "postgresql://"):
            if value.startswith(scheme):
                return "postgresql+psycopg://" + value[len(scheme) :]
        return value

    @field_validator("agricultural_thresholds_path", mode="before")
    @classmethod
    def empty_threshold_path_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def validate_agricultural_runtime(self) -> "Settings":
        if self.rag_embedding_dimension != 1536:
            raise ValueError("RAG_EMBEDDING_DIMENSION must match pgvector's fixed 1536 dimensions")
        if self.embedding_provider == "alibaba":
            if not self.dashscope_api_key:
                raise ValueError("DASHSCOPE_API_KEY is required when EMBEDDING_PROVIDER=alibaba")
            if not self.dashscope_base_url:
                raise ValueError(
                    "DASHSCOPE_BASE_URL is required when EMBEDDING_PROVIDER=alibaba"
                )
        if self.embedding_provider == "cohere" and not self.cohere_api_key:
            raise ValueError("COHERE_API_KEY is required when EMBEDDING_PROVIDER=cohere")
        if self.app_env == "production":
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required in production")
            if not self.rag_trusted_publishers:
                raise ValueError("RAG_TRUSTED_PUBLISHERS must include approved publishers")
            if self.rag_minimum_score <= 0:
                raise ValueError("RAG_MINIMUM_SCORE must be calibrated and greater than zero")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=PROJECT_ROOT / ".env")
