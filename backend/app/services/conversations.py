"""Conversational orchestration service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agriculture.engine import AgriculturalDecisionEngine
from app.conversation.agricultural_pipeline import AgriculturalChatPipeline
from app.conversation.agricultural_tools import (
    DatabaseFarmerContextTool,
    DatabaseWeatherContextTool,
)
from app.conversation.explanation import WeatherExplanationService
from app.conversation.intents import WeatherIntent, detect_intent
from app.conversation.weather_tool import WeatherResult, WeatherTool
from app.domain.models import Conversation, Message, MessageRole
from app.schemas.conversation import ConversationMessageRequest


class ConversationNotFoundError(Exception):
    """Raised when a conversation is not owned by the requesting user."""


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
    if _is_agricultural_question(request.content):
        try:
            agricultural_result = AgriculturalChatPipeline(
                DatabaseFarmerContextTool(session),
                DatabaseWeatherContextTool(session),
                AgriculturalDecisionEngine(),
            ).answer(
                user_id,
                request.content,
                language=request.language,
                farm_id=request.farm_id or conversation.farm_id,
            )
        except ValueError:
            agricultural_result = None
    result = (
        None
        if agricultural_result is not None
        else WeatherTool(session, user_id, request.farm_id or conversation.farm_id).run(intent)
    )
    explanation = (
        agricultural_result.explanation
        if agricultural_result is not None
        else WeatherExplanationService().explain(result, request.language)
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=explanation,
    )
    session.add(assistant_message)
    session.flush()
    return conversation, assistant_message, intent, agricultural_result or result


def _is_agricultural_question(content: str) -> bool:
    normalized = content.casefold()
    return any(
        term in normalized
        for term in (
            "irrigat",
            "spray",
            "pesticide",
            "sow",
            "plant",
            "seed",
            "soybean",
            "फवार",
            "पाणी",
        )
    )
