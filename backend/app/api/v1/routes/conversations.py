"""Conversational weather API."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.conversation.agricultural_pipeline import AgriculturalPipelineResult
from app.conversation.gemini import GeminiError
from app.schemas.conversation import (
    AgriculturalMetadata,
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationResponse,
    WeatherMetadata,
)
from app.services.conversations import (
    AgriculturalKnowledgeResult,
    ConversationNotFoundError,
    handle_message,
)

router = APIRouter(prefix="/conversations")


@router.post("/messages", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    request: ConversationMessageRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ConversationResponse:
    try:
        conversation, message, intent, result = handle_message(session, user.id, request)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    except GeminiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    session.commit()
    session.refresh(message)
    agricultural_result = result if isinstance(result, AgriculturalPipelineResult) else None
    knowledge_result = result if isinstance(result, AgriculturalKnowledgeResult) else None
    weather_result = result if not agricultural_result and not knowledge_result else None
    agricultural = None
    if agricultural_result is not None:
        agricultural = AgriculturalMetadata(
            decision_type=agricultural_result.decision.decision_type.value,
            decision=agricultural_result.decision.decision.value,
            risk_level=agricultural_result.decision.risk_level.value,
            confidence=agricultural_result.decision.confidence,
            reasons=list(agricultural_result.decision.reasons),
            deterministic=agricultural_result.decision.deterministic,
            citations=agricultural_result.citations,
        )
    metadata = WeatherMetadata(
        intent=intent.value,
        farm_id=(
            agricultural_result.farmer.farm_id
            if agricultural_result
            else weather_result.farm_id
            if weather_result
            else None
        ),
        farm_name=(
            agricultural_result.farmer.farm_name
            if agricultural_result
            else weather_result.farm_name
            if weather_result
            else None
        ),
        current=weather_result.current if weather_result else None,
        forecast=weather_result.forecast if weather_result else None,
        rainfall_mm=weather_result.rainfall_mm if weather_result else None,
        alerts=weather_result.alerts if weather_result else None,
        source=weather_result.source if weather_result else None,
        agricultural=agricultural,
        knowledge_sources=(
            agricultural_result.citations
            if agricultural_result
            else knowledge_result.citations
            if knowledge_result
            else []
        ),
    )
    return ConversationResponse(
        conversation_id=conversation.id,
        message=ConversationMessageResponse(
            id=message.id,
            role=message.role.value,
            content=message.content,
            created_at=message.created_at,
            metadata=metadata,
        ),
    )
