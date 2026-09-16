"""Tool-oriented orchestration for agricultural chatbot questions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.types import AgriculturalInputs, Decision, DecisionType, WeatherSnapshot
from app.rag.retrieval import RetrievalService
from app.rag.types import RetrievedChunk


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
    # This small vocabulary prevents a question about a crop that is not active on
    # the selected farm (for example, "wheat" on a soybean farm) from silently
    # being evaluated as the farm's first crop.  Farm crops still take priority.
    _common_crops = (
        "rice", "wheat", "maize", "corn", "soybean", "cotton", "sugarcane",
        "chickpea", "gram", "pigeon pea", "tomato", "potato", "onion",
        "groundnut", "millet", "sorghum",
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
        crops = tuple(dict.fromkeys((*known_crops, *self._common_crops)))
        crop = next((item for item in crops if item.casefold() in normalized), None)
        # A crop/farm-weather question without a named action is still useful to
        # route through the compatibility rule.  It avoids falling back to a
        # generic weather answer that discards the farmer's context.
        if action is None and any(
            term in normalized
            for term in (
                "crop", "farm", "field", "growing", "disease", "pest", "fertil",
                "harvest", "yield", "पीक", "शेत", "फसल", "खेती",
            )
        ):
            action = DecisionType.CROP_WEATHER_COMPATIBILITY
        return ExtractedEntities(
            location=profile_location,
            crop=crop,
            growth_stage=growth_stage,
            requested_action=action,
            # Retrieved material complements every deterministic decision; it
            # never replaces its verdict.  This is especially useful for safe
            # follow-up steps after irrigation and weather-risk decisions.
            knowledge_required=action is not None,
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

    def list_crops(self, user_id: UUID, farm_id: UUID | None) -> tuple[str, ...]: ...


class WeatherContextTool(Protocol):
    def get_context(self, farm_id: UUID) -> WeatherContext: ...


class AgriculturalExplanation(Protocol):
    def explain(
        self,
        question: str,
        decision: Decision,
        farmer: FarmerContext,
        weather: WeatherContext,
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
        weather: WeatherContext,
        retrieved: list[RetrievedChunk],
        language: str,
    ) -> str:
        farm_details = ", ".join(
            f"{label}={value}"
            for label, value in (
                ("farm", farmer.farm_name),
                ("location", farmer.location),
                ("crop", farmer.crop),
                ("growth stage", farmer.growth_stage),
                ("soil", farmer.soil_type),
                ("irrigation", farmer.irrigation_type),
                (
                    "soil moisture",
                    f"{farmer.soil_moisture_percent}%"
                    if farmer.soil_moisture_percent is not None
                    else None,
                ),
            )
            if value is not None
        )
        weather_pairs = (
            (
                "recent rainfall",
                f"{weather.recent_rainfall_mm} mm"
                if weather.recent_rainfall_mm is not None
                else None,
            ),
            (
                "forecast rainfall",
                f"{weather.forecast_rainfall_mm} mm"
                if weather.forecast_rainfall_mm is not None
                else None,
            ),
            (
                "temperature",
                f"{weather.temperature_celsius}°C"
                if weather.temperature_celsius is not None
                else None,
            ),
            (
                "humidity",
                f"{weather.humidity_percent}%" if weather.humidity_percent is not None else None,
            ),
            (
                "wind",
                f"{weather.wind_speed_kph} kph" if weather.wind_speed_kph is not None else None,
            ),
        )
        weather_details = ", ".join(
            f"{label}={value}"
            for label, value in weather_pairs
            if value is not None
        )
        explanation = (
            f"Decision: {decision.decision.value}. Reasons: {'; '.join(decision.reasons)}."
        )
        if farm_details:
            explanation += f" Farm context: {farm_details}."
        if weather_details:
            explanation += f" Verified weather: {weather_details}."
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
        list_crops = getattr(self.farmer_tool, "list_crops", None)
        known_crops = list_crops(user_id, farm_id) if callable(list_crops) else ()
        entities = self.extractor.extract(
            question,
            known_crops=known_crops or ((initial.crop,) if initial.crop else ()),
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
            retrieval_query = self._retrieval_query(question, farmer, weather, entities)
            # Run one vector search, then prefer same-language material in its
            # ranked results. This keeps cross-language fallbacks available
            # without a second query when official guidance is English-only.
            candidates = self.retrieval_service.retrieve(retrieval_query)
            retrieved = sorted(
                candidates,
                key=lambda item: (item.chunk.metadata.language != language, -item.score),
            )
        explanation = self.explanation.explain(
            question, decision, farmer, weather, retrieved, language
        )
        return AgriculturalPipelineResult(
            entities,
            farmer,
            weather,
            decision,
            tuple(retrieved),
            explanation,
            datetime.now(UTC),
        )

    @staticmethod
    def _retrieval_query(
        question: str,
        farmer: FarmerContext,
        weather: WeatherContext,
        entities: ExtractedEntities,
    ) -> str:
        return " ".join(
            str(value)
            for value in (
                question,
                entities.requested_action.value if entities.requested_action else None,
                farmer.crop,
                farmer.growth_stage,
                farmer.soil_type,
                farmer.irrigation_type,
                f"soil moisture {farmer.soil_moisture_percent} percent"
                if farmer.soil_moisture_percent is not None
                else None,
                f"rainfall {weather.recent_rainfall_mm} mm"
                if weather.recent_rainfall_mm is not None
                else None,
                f"forecast rainfall {weather.forecast_rainfall_mm} mm"
                if weather.forecast_rainfall_mm is not None
                else None,
            )
            if value
        )
