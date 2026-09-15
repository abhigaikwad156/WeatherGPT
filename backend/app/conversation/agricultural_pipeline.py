"""Tool-oriented orchestration for agricultural chatbot questions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.types import AgriculturalInputs, Decision, DecisionType, WeatherSnapshot
from app.rag.retrieval import RetrievalService
from app.rag.types import RetrievalFilter, RetrievedChunk


@dataclass(frozen=True)
class ExtractedEntities:
    location: str | None
    crop: str | None
    growth_stage: str | None
    requested_action: DecisionType | None
    knowledge_required: bool


class IntentEntityExtractor:
    """Conservative extraction; it identifies terms but does not make decisions."""

    _actions: tuple[tuple[DecisionType, tuple[str, ...]], ...] = (
        (
            DecisionType.IRRIGATION,
            ("irrigat", "water", "पाणी", "सिंचन", "सिंचाई", "पानी"),
        ),
        (
            DecisionType.SPRAYING,
            ("spray", "pesticide", "फवार", "स्प्रे", "छिड़काव", "कीटनाशक"),
        ),
        (
            DecisionType.SOWING_WINDOW,
            ("sow", "plant", "seed", "पेर", "लाव", "बोना", "बुवाई"),
        ),
        (
            DecisionType.EXTREME_WEATHER,
            ("risk", "storm", "frost", "heat", "warning", "वादळ", "तूफान", "लू"),
        ),
        (
            DecisionType.CROP_WEATHER_COMPATIBILITY,
            ("suitable", "compatible", "fit", "योग्य", "अनुकूल"),
        ),
    )

    def extract(
        self,
        question: str,
        *,
        known_crops: tuple[str, ...] = (),
        profile_location: str | None = None,
        growth_stage: str | None = None,
    ) -> ExtractedEntities:
        normalized = " ".join(question.casefold().split())
        action = next(
            (
                decision_type
                for decision_type, terms in self._actions
                if any(term in normalized for term in terms)
            ),
            None,
        )
        crop = next((item for item in known_crops if item.casefold() in normalized), None)
        return ExtractedEntities(
            location=profile_location,
            crop=crop,
            growth_stage=growth_stage,
            requested_action=action,
            knowledge_required=action
            in {
                DecisionType.SPRAYING,
                DecisionType.SOWING_WINDOW,
                DecisionType.CROP_WEATHER_COMPATIBILITY,
            },
        )


@dataclass(frozen=True)
class FarmerContext:
    farm_id: UUID
    farm_name: str
    location: str | None
    soil_type: str | None
    irrigation_type: str | None
    soil_moisture_percent: float | None
    crop: str | None
    growth_stage: str | None


@dataclass(frozen=True)
class WeatherContext:
    recent_rainfall_mm: float | None
    forecast_rainfall_mm: float | None
    temperature_celsius: float | None
    humidity_percent: float | None
    wind_speed_kph: float | None
    historical_weather: tuple[WeatherSnapshot, ...] = ()
    forecast_weather: tuple[WeatherSnapshot, ...] = ()


class FarmerContextTool(Protocol):
    def get_context(
        self, user_id: UUID, farm_id: UUID | None, crop: str | None
    ) -> FarmerContext | None: ...


class WeatherContextTool(Protocol):
    def get_context(self, farm_id: UUID) -> WeatherContext: ...


class AgriculturalExplanation(Protocol):
    def explain(
        self,
        question: str,
        decision: Decision,
        farmer: FarmerContext,
        retrieved: list[RetrievedChunk],
        language: str,
    ) -> str: ...


class GroundedExplanation:
    """Presentation boundary; it cannot change the deterministic decision."""

    def explain(
        self,
        question: str,
        decision: Decision,
        farmer: FarmerContext,
        retrieved: list[RetrievedChunk],
        language: str,
    ) -> str:
        explanation = f"{decision.decision.value}: {'; '.join(decision.reasons)}"
        if retrieved:
            sources = ", ".join(item.chunk.metadata.title for item in retrieved)
            explanation += f" Verified guidance: {sources}."
        return explanation


@dataclass(frozen=True)
class AgriculturalPipelineResult:
    entities: ExtractedEntities
    farmer: FarmerContext
    weather: WeatherContext
    decision: Decision
    retrieved: tuple[RetrievedChunk, ...]
    explanation: str
    generated_at: datetime

    @property
    def citations(self) -> list[dict[str, object]]:
        return [
            {
                "source_id": item.chunk.metadata.source_id,
                "title": item.chunk.metadata.title,
                "publisher": item.chunk.metadata.publisher,
                "source_uri": item.chunk.metadata.source_uri,
            }
            for item in self.retrieved
        ]


class AgriculturalChatPipeline:
    def __init__(
        self,
        farmer_tool: FarmerContextTool,
        weather_tool: WeatherContextTool,
        decision_engine: AgriculturalDecisionEngine,
        retrieval_service: RetrievalService | None = None,
        extractor: IntentEntityExtractor | None = None,
        explanation: AgriculturalExplanation | None = None,
    ) -> None:
        self.farmer_tool = farmer_tool
        self.weather_tool = weather_tool
        self.decision_engine = decision_engine
        self.retrieval_service = retrieval_service
        self.extractor = extractor or IntentEntityExtractor()
        self.explanation = explanation or GroundedExplanation()

    def answer(
        self,
        user_id: UUID,
        question: str,
        *,
        language: str = "mr",
        farm_id: UUID | None = None,
    ) -> AgriculturalPipelineResult:
        initial = self.farmer_tool.get_context(user_id, farm_id, None)
        if initial is None:
            raise ValueError("No owned farm is available for this question")
        entities = self.extractor.extract(
            question,
            known_crops=(initial.crop,) if initial.crop else (),
            profile_location=initial.location,
            growth_stage=initial.growth_stage,
        )
        farmer = self.farmer_tool.get_context(user_id, farm_id, entities.crop)
        if farmer is None:
            raise ValueError("No matching farmer crop is available for this question")
        if entities.requested_action is None:
            raise ValueError("The requested agricultural action could not be identified")
        weather = self.weather_tool.get_context(farmer.farm_id)
        agricultural_inputs = AgriculturalInputs(
            crop=farmer.crop,
            growth_stage=farmer.growth_stage,
            soil_type=farmer.soil_type,
            irrigation_type=farmer.irrigation_type,
            recent_rainfall_mm=weather.recent_rainfall_mm,
            forecast_rainfall_mm=weather.forecast_rainfall_mm,
            temperature_celsius=weather.temperature_celsius,
            humidity_percent=weather.humidity_percent,
            wind_speed_kph=weather.wind_speed_kph,
            soil_moisture_percent=farmer.soil_moisture_percent,
            historical_weather=weather.historical_weather,
            forecast_weather=weather.forecast_weather,
        )
        decision = self.decision_engine.evaluate(agricultural_inputs)[entities.requested_action]
        retrieved: list[RetrievedChunk] = []
        if entities.knowledge_required and self.retrieval_service:
            retrieved = self.retrieval_service.retrieve(
                question,
                filters=RetrievalFilter(language=language),
            )
        explanation = self.explanation.explain(question, decision, farmer, retrieved, language)
        return AgriculturalPipelineResult(
            entities,
            farmer,
            weather,
            decision,
            tuple(retrieved),
            explanation,
            datetime.now(UTC),
        )
