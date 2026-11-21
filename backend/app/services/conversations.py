"""Conversational orchestration service."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import AgriculturalThresholds, load_default_thresholds
from app.agriculture.types import DecisionType
from app.conversation.agricultural_pipeline import AgriculturalChatPipeline
from app.conversation.agricultural_tools import (
    DatabaseFarmerContextTool,
    DatabaseWeatherContextTool,
)
from app.conversation.explanation import WeatherExplanationService
from app.conversation.gemini import GeminiChatService
from app.conversation.intents import WeatherIntent, detect_intent
from app.conversation.weather_tool import WeatherResult, WeatherTool
from app.core.config import get_settings
from app.domain.models import Conversation, Message, MessageRole
from app.rag.embeddings import create_embedding_provider
from app.rag.postgres import PgVectorChunkRepository
from app.rag.retrieval import RetrievalService
from app.schemas.conversation import ConversationMessageRequest
from app.services.recommendations import persist_irrigation_recommendation


class ConversationNotFoundError(Exception):
    """Raised when a conversation is not owned by the requesting user."""


@dataclass(frozen=True)
class AgriculturalKnowledgeResult:
    """Source metadata for agricultural answers that do not produce a rule decision."""

    citations: list[dict[str, object]]


def handle_message(
    session: Session, user_id: UUID, request: ConversationMessageRequest
) -> tuple[Conversation, Message, WeatherIntent, WeatherResult | None]:
    conversation = None
    if request.conversation_id is not None:
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.user_id == user_id,
            )
        )
        if conversation is None:
            raise ConversationNotFoundError
    if conversation is None:
        conversation = Conversation(
            user_id=user_id, farm_id=request.farm_id, language=request.language
        )
        session.add(conversation)
        session.flush()

    intent = detect_intent(request.content)
    user_message = Message(
        conversation_id=conversation.id,
        sender_id=user_id,
        role=MessageRole.USER,
        content=request.content,
    )
    session.add(user_message)
    session.flush()

    agricultural_result = None
    knowledge_result = None
    retrieval_service = None
    agricultural_question = intent == WeatherIntent.UNKNOWN or _is_agricultural_question(
        request.content
    )
    if agricultural_question:
        try:
            retrieval_service = _retrieval_service(session)
            agricultural_result = AgriculturalChatPipeline(
                DatabaseFarmerContextTool(session),
                DatabaseWeatherContextTool(session),
                AgriculturalDecisionEngine(_load_thresholds()),
                retrieval_service,
            ).answer(
                user_id,
                request.content,
                language=request.language,
                farm_id=request.farm_id or conversation.farm_id,
            )
            if agricultural_result.decision.decision_type == DecisionType.IRRIGATION:
                persist_irrigation_recommendation(
                    session,
                    user_id,
                    agricultural_result.farmer.farm_id,
                    agricultural_result.farmer.farmer_crop_id,
                    agricultural_result.decision,
                    generated_at=agricultural_result.generated_at,
                )
        except ValueError:
            agricultural_result = None
    if agricultural_question and agricultural_result is None:
        if retrieval_service is None:
            retrieval_service = _retrieval_service(session)
        retrieved = retrieval_service.retrieve(request.content)
        sources = RetrievalService.context(retrieved)
        knowledge_result = AgriculturalKnowledgeResult(
            citations=[item["source"] for item in sources]
        )
    result = (
        None
        if agricultural_result is not None
        else WeatherTool(session, user_id, request.farm_id or conversation.farm_id).run(intent)
    )
    fallback_explanation = (
        agricultural_result.explanation
        if agricultural_result is not None
        else _knowledge_context(request.content, sources, result, request.language)
        if knowledge_result is not None
        else _agricultural_help()
        if agricultural_question and result is None
        else WeatherExplanationService().explain(result, request.language)
    )
    if (
        agricultural_result is not None
        and agricultural_result.decision.decision_type == DecisionType.IRRIGATION
    ):
        explanation = agricultural_result.explanation
    elif agricultural_result is not None and not agricultural_result.retrieved:
        explanation = agricultural_result.explanation
    elif knowledge_result is not None and not knowledge_result.citations:
        explanation = _no_verified_source_fallback(request.language)
    else:
        explanation = GeminiChatService(get_settings()).respond(
            request.content, request.language, fallback_explanation
        )
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=explanation,
    )
    session.add(assistant_message)
    session.flush()
    return (
        conversation,
        assistant_message,
        intent,
        agricultural_result or knowledge_result or result,
    )


def _is_agricultural_question(content: str) -> bool:
    normalized = content.casefold()
    return any(
        term in normalized
        for term in (
            "irrigat",
            "water",
            "spray",
            "pesticide",
            "fertil",
            "disease",
            "pest",
            "farm",
            "field",
            "crop",
            "soil",
            "sugarcane",
            "sugar cane",
            "rainfall",
            "heavy rain",
            "कृषि",
            "गन्ना",
            "ऊस",
            "कांदा",
            "माती",
            "मृदा",
            "खत",
            "रोग",
            "कीड",
            "पाऊस",
            "सिंचन",
        )
    )


def _retrieval_service(session: Session) -> RetrievalService:
    """Build the pgvector-backed RAG service with the migration's 1536 dimensions."""
    settings = get_settings()
    repository = PgVectorChunkRepository(session.get_bind())
    embeddings = create_embedding_provider(settings)
    return RetrievalService(repository, embeddings, settings.rag_minimum_score)


def _load_thresholds() -> AgriculturalThresholds:
    path = get_settings().agricultural_thresholds_path
    return AgriculturalThresholds.from_json(path) if path else load_default_thresholds()


def _agricultural_help() -> str:
    return (
        "I can help with irrigation, spraying, sowing, and weather risk. "
        "Try a specific question such as 'Should I irrigate today?' or 'Is it safe to spray?'"
    )


def _no_verified_source_fallback(language: str) -> str:
    language_code = language.split("-", maxsplit=1)[0].casefold()
    if language_code == "mr":
        return (
            "या प्रश्नासाठी संबंधित सत्यापित कृषी स्रोत सापडला नाही, त्यामुळे मी स्रोताधारित उत्तर देऊ शकत नाही."
        )
    if language_code == "hi":
        return (
            "इस प्रश्न के लिए कोई संबंधित सत्यापित कृषि स्रोत नहीं मिला, "
            "इसलिए मैं स्रोत-आधारित उत्तर नहीं दे सकता।"
        )
    return (
        "I couldn't find a relevant verified agricultural source for this question, "
        "so I can't provide a source-grounded answer."
    )


def _knowledge_context(
    question: str,
    sources: list[dict[str, object]],
    weather_result: WeatherResult | None,
    language: str,
) -> str:
    sections = [f"Agricultural question: {question}"]
    if sources:
        sections.append(
            "Retrieved agricultural source excerpts (cite the title and publisher):\n"
            + json.dumps(sources, ensure_ascii=False)
        )
    else:
        sections.append("No verified agricultural source excerpts matched this question.")
    if weather_result is not None:
        sections.append(WeatherExplanationService().explain(weather_result, language))
    return "\n\n".join(sections)
