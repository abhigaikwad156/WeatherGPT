"""Conversational API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="mr", min_length=2, max_length=10)
    conversation_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("conversation_id", "conversationId"),
    )
    farm_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("farm_id", "farmId"),
    )


class AgriculturalMetadata(BaseModel):
    decision_type: str = Field(serialization_alias="decisionType")
    decision: str
    risk_level: str = Field(serialization_alias="riskLevel")
    confidence: float
    reasons: list[str]
    deterministic: bool
    citations: list[dict[str, object]] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class WeatherMetadata(BaseModel):
    intent: str
    farm_id: UUID | None = Field(default=None, serialization_alias="farmId")
    farm_name: str | None = Field(default=None, serialization_alias="farmName")
    current: dict[str, object] | None = None
    forecast: list[dict[str, object]] | None = None
    rainfall_mm: float | None = Field(default=None, serialization_alias="rainfallMm")
    alerts: list[dict[str, object]] | None = None
    source: str | None = None
    agricultural: AgriculturalMetadata | None = None

    model_config = ConfigDict(populate_by_name=True)


class ConversationMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime | None = Field(default=None, serialization_alias="createdAt")
    metadata: WeatherMetadata | None = None

    model_config = ConfigDict(populate_by_name=True)


class ConversationResponse(BaseModel):
    conversation_id: UUID = Field(serialization_alias="conversationId")
    message: ConversationMessageResponse

    model_config = ConfigDict(populate_by_name=True)
