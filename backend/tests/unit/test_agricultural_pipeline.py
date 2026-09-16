from datetime import UTC, datetime
from uuid import uuid4

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import (
    AgriculturalThresholds,
    CropProfile,
    IrrigationForecast,
    IrrigationProfile,
    IrrigationProfileSource,
    IrrigationSoilMoisture,
)
from app.agriculture.types import DecisionType, DecisionValue, WeatherSnapshot
from app.conversation.agricultural_pipeline import (
    AgriculturalChatPipeline,
    FarmerContext,
    WeatherContext,
)
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.ingestion import DocumentIngestionService
from app.rag.repository import InMemoryChunkRepository
from app.rag.retrieval import RetrievalService
from app.rag.types import SourceMetadata

FARM_ID = uuid4()
USER_ID = uuid4()


class FarmerTool:
    def get_context(self, user_id: object, farm_id: object, crop: str | None) -> FarmerContext:
        return FarmerContext(
            FARM_ID, "Green Farm", "Pune", "loam", "drip", 40, "soybean", "vegetative"
        )


class WeatherTool:
    def get_context(self, farm_id: object, *, forecast_horizon_days: int = 3) -> WeatherContext:
        return WeatherContext(
            4,
            12,
            24,
            60,
            8,
            forecast_horizon_days,
            forecast_weather=(WeatherSnapshot(datetime.now(UTC), rainfall_mm=12),),
        )


def engine() -> AgriculturalDecisionEngine:
    return AgriculturalDecisionEngine(
        AgriculturalThresholds(
            # Numeric values here are isolated test fixtures; production JSON
            # intentionally contains no irrigation-profile threshold values.
            irrigation_profiles=(
                IrrigationProfile(
                    crop="soybean",
                    growth_stage="vegetative",
                    soil_type="loam",
                    irrigation_type="drip",
                    region="Pune",
                    soil_moisture=IrrigationSoilMoisture(sufficient_percent=60),
                    forecast=IrrigationForecast(rainfall_lookahead_mm=10, horizon_days=3),
                    source=IrrigationProfileSource(reviewed_by="Test agronomist"),
                ),
            ),
            spray_rainfall_lookahead_mm=2,
            spray_min_humidity_percent=40,
            spray_max_humidity_percent=80,
            spray_max_wind_speed_kph=15,
            sowing_min_temperature_celsius=18,
            sowing_max_temperature_celsius=32,
            sowing_rainfall_min_mm=5,
            sowing_rainfall_max_mm=25,
            crop_profiles={"soybean": CropProfile(15, 35)},
        )
    )


def pipeline(retrieval: RetrievalService | None = None) -> AgriculturalChatPipeline:
    return AgriculturalChatPipeline(FarmerTool(), WeatherTool(), engine(), retrieval)


def test_five_farmer_questions_run_through_tools_and_engine() -> None:
    questions = (
        ("Should I irrigate my soybean tomorrow?", DecisionType.IRRIGATION, DecisionValue.WAIT),
        ("Should I spray my soybean?", DecisionType.SPRAYING, DecisionValue.WAIT),
        ("Can I sow soybean now?", DecisionType.SOWING_WINDOW, DecisionValue.SUITABLE),
        ("Is there extreme weather risk?", DecisionType.EXTREME_WEATHER, DecisionValue.NEEDS_INPUT),
        (
            "Is the weather suitable for soybean?",
            DecisionType.CROP_WEATHER_COMPATIBILITY,
            DecisionValue.SUITABLE,
        ),
    )
    for question, decision_type, expected in questions:
        result = pipeline().answer(USER_ID, question, language="en", farm_id=FARM_ID)
        assert result.entities.requested_action == decision_type
        assert result.decision.decision == expected
        assert result.decision.deterministic is True
        assert result.decision.llm_explanation is None


def test_agricultural_knowledge_is_retrieved_with_citations() -> None:
    repository = InMemoryChunkRepository()
    ingestion = DocumentIngestionService(
        repository, HashEmbeddingProvider(), {"Agriculture Department"}
    )
    ingestion.ingest(
        b"Spraying should follow the approved product label and local guidance.",
        "text/plain",
        SourceMetadata(
            "spray-1",
            "Spraying guide",
            "Agriculture Department",
            language="en",
            trusted=True,
        ),
    )
    result = pipeline(RetrievalService(repository, HashEmbeddingProvider())).answer(
        USER_ID, "Should I spray my soybean?", language="en", farm_id=FARM_ID
    )
    assert result.retrieved
    assert result.citations[0]["source_id"] == "spray-1"
    assert "Spraying guide" in result.explanation


def test_generic_crop_question_keeps_farm_and_weather_context() -> None:
    result = pipeline().answer(
        USER_ID,
        "How is the weather affecting my crop today?",
        language="en",
        farm_id=FARM_ID,
    )

    assert result.entities.requested_action == DecisionType.CROP_WEATHER_COMPATIBILITY
    assert "Farm context: farm=Green Farm" in result.explanation
    assert "crop=soybean" in result.explanation
    assert "Verified weather: recent rainfall=4 mm" in result.explanation
    assert "forecast rainfall=12 mm" in result.explanation


def test_retrieval_query_includes_crop_farm_and_weather_signals() -> None:
    result = pipeline().answer(
        USER_ID, "Should I irrigate my soybean tomorrow?", language="en", farm_id=FARM_ID
    )
    query = AgriculturalChatPipeline._retrieval_query(
        "Should I irrigate my soybean tomorrow?",
        result.farmer,
        result.weather,
        result.entities,
    )

    assert "irrigation" in query
    assert "soybean" in query
    assert "vegetative" in query
    assert "loam" in query
    assert "drip" in query
    assert "soil moisture 40 percent" in query
    assert "forecast rainfall 12 mm" in query
