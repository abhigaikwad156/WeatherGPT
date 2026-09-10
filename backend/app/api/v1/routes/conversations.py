"""Conversational weather API."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DatabaseSession
from app.conversation.agricultural_pipeline import AgriculturalPipelineResult
from app.schemas.conversation import (
    AgriculturalMetadata,
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationResponse,
    WeatherMetadata,
)
from app.services.conversations import ConversationNotFoundError, handle_message

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
    session.commit()
    session.refresh(message)
    agricultural = None
    if isinstance(result, AgriculturalPipelineResult):
        agricultural = AgriculturalMetadata(
            decision_type=result.decision.decision_type.value,
            decision=result.decision.decision.value,
            risk_level=result.decision.risk_level.value,
            confidence=result.decision.confidence,
            reasons=list(result.decision.reasons),
            deterministic=result.decision.deterministic,
            citations=result.citations,
        )
    metadata = WeatherMetadata(
        intent=intent.value,
        farm_id=(
            agricultural.farmer.farm_id if agricultural else result.farm_id if result else None
        ),
        farm_name=(
            agricultural.farmer.farm_name if agricultural else result.farm_name if result else None
        ),
        current=result.current if result and not agricultural else None,
        forecast=result.forecast if result and not agricultural else None,
        rainfall_mm=result.rainfall_mm if result and not agricultural else None,
        alerts=result.alerts if result and not agricultural else None,
        source=result.source if result and not agricultural else None,
        agricultural=agricultural,
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
