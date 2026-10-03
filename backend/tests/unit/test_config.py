import pytest
from pydantic import ValidationError

from app.agriculture.thresholds import AgriculturalThresholds
from app.core.config import Settings


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


def test_settings_treats_blank_threshold_path_as_unset() -> None:
    assert Settings(agricultural_thresholds_path="").agricultural_thresholds_path is None


def test_production_requires_calibrated_rag_and_trusted_publishers() -> None:
    with pytest.raises(ValidationError, match="RAG_MINIMUM_SCORE"):
        Settings(
            app_env="production",
            jwt_secret_key="x" * 32,
            gemini_api_key="test-key",
            rag_trusted_publishers=["Approved Department"],
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
