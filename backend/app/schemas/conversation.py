"""Conversational API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="mr", min_length=2, max_length=10)
    conversation_id: UUID | None = None
    farm_id: UUID | None = None


class AgriculturalMetadata(BaseModel):
    decision_type: str
    decision: str
    risk_level: str
    confidence: float
    reasons: list[str]
    deterministic: bool
    citations: list[dict[str, object]] = Field(default_factory=list)


class WeatherMetadata(BaseModel):
    intent: str
    farm_id: UUID | None = None
    farm_name: str | None = None
    current: dict[str, object] | None = None
    forecast: list[dict[str, object]] | None = None
    rainfall_mm: float | None = None
    alerts: list[dict[str, object]] | None = None
    source: str | None = None
    agricultural: AgriculturalMetadata | None = None


class ConversationMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime | None = None
    metadata: WeatherMetadata | None = None


class ConversationResponse(BaseModel):
    conversation_id: UUID
    message: ConversationMessageResponse
