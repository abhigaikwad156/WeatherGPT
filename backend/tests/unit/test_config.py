import pytest
from pydantic import ValidationError

from app.agriculture.thresholds import AgriculturalThresholds
from app.core.config import Settings
from app.rag.embeddings import (
    AlibabaEmbeddingProvider,
    CohereEmbeddingProvider,
    create_embedding_provider,
)


def test_settings_rejects_cors_wildcard() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(cors_origins=["*"])


def test_settings_uses_explicit_local_cors_origin() -> None:
    assert Settings().cors_origins == [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]


def test_settings_rejects_rag_dimension_that_does_not_match_pgvector() -> None:
    with pytest.raises(ValidationError, match="1536"):
        Settings(rag_embedding_dimension=768)


def test_settings_configures_alibaba_embeddings() -> None:
    settings = Settings(
        embedding_provider="alibaba",
        dashscope_api_key="test-key",
        dashscope_base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    )

    assert settings.embedding_provider == "alibaba"
    assert settings.rag_embedding_dimension == 1536


def test_embedding_provider_factory_selects_alibaba_for_rag() -> None:
    settings = Settings(
        embedding_provider="alibaba",
        dashscope_api_key="test-key",
        dashscope_base_url="https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    )

    provider = create_embedding_provider(settings)

    assert isinstance(provider, AlibabaEmbeddingProvider)
    assert provider.dimension == 1536
    assert provider.model_name == "text-embedding-v4"


def test_embedding_provider_factory_selects_cohere_for_rag() -> None:
    settings = Settings(embedding_provider="cohere", cohere_api_key="test-key")

    provider = create_embedding_provider(settings)

    assert isinstance(provider, CohereEmbeddingProvider)
    assert provider.dimension == 1536
    assert provider.model_name == "embed-v4.0"


def test_settings_requires_cohere_api_key() -> None:
    with pytest.raises(ValidationError, match="COHERE_API_KEY"):
        Settings(embedding_provider="cohere", cohere_api_key=None)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("dashscope_api_key", "DASHSCOPE_API_KEY"),
        ("dashscope_base_url", "DASHSCOPE_BASE_URL"),
    ],
)
def test_settings_requires_alibaba_credentials_and_endpoint(field: str, message: str) -> None:
    values = {
        "embedding_provider": "alibaba",
        "dashscope_api_key": "test-key",
        "dashscope_base_url": "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    }
    values[field] = None

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_settings_uses_a_relevance_threshold_for_rag() -> None:
    assert Settings(jwt_secret_key="x" * 32).rag_minimum_score == 0.55


@pytest.mark.parametrize("scheme", ("postgres://", "postgresql://"))
def test_settings_uses_installed_psycopg_driver(scheme: str) -> None:
    settings = Settings(
        database_url=f"{scheme}user:password@db.example/weathergpt",
        jwt_secret_key="x" * 32,
    )

    assert settings.database_url == (
        "postgresql+psycopg://user:password@db.example/weathergpt"
    )


def test_settings_treats_blank_threshold_path_as_unset() -> None:
    assert Settings(agricultural_thresholds_path="").agricultural_thresholds_path is None


def test_production_requires_calibrated_rag_and_trusted_publishers() -> None:
    with pytest.raises(ValidationError, match="RAG_MINIMUM_SCORE"):
        Settings(
            app_env="production",
            jwt_secret_key="x" * 32,
            gemini_api_key="test-key",
            rag_trusted_publishers=["Approved Department"],
            rag_minimum_score=0,
        )


def test_threshold_file_rejects_enabled_value_without_source_note(tmp_path) -> None:
    path = tmp_path / "thresholds.json"
    path.write_text(
        '{"spray_max_wind_speed_kph": 12, "source_notes": {}}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="source_notes.spray_max_wind_speed_kph"):
        AgriculturalThresholds.from_json(path)


def test_threshold_file_accepts_traced_enabled_value(tmp_path) -> None:
    path = tmp_path / "thresholds.json"
    path.write_text(
        '{"spray_max_wind_speed_kph": 12, '
        '"source_notes": {"spray_max_wind_speed_kph": "Reviewed local guide, 2026"}}',
        encoding="utf-8",
    )

    thresholds = AgriculturalThresholds.from_json(path)

    assert thresholds.spray_max_wind_speed_kph == 12
