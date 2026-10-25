"""Read-only deterministic agricultural recommendation responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DecisionRecommendation(BaseModel):
    id: str
    recommendation_type: str = Field(serialization_alias="recommendationType")
    crop_id: UUID | None = Field(serialization_alias="cropId")
    crop_name: str | None = Field(serialization_alias="cropName")
    decision: str
    risk_level: str = Field(serialization_alias="riskLevel")
    confidence: float
    status: Literal["available", "needs_input"]
    reasons: list[str]

    model_config = ConfigDict(populate_by_name=True)


class FarmRecommendations(BaseModel):
    farm_id: UUID = Field(serialization_alias="farmId")
    farm_name: str = Field(serialization_alias="farmName")
    weather_provider: str = Field(serialization_alias="weatherProvider")
    weather_fetched_at: datetime = Field(serialization_alias="weatherFetchedAt")
    status: Literal["available", "insufficient_data"]
    recommendations: list[DecisionRecommendation]

    model_config = ConfigDict(populate_by_name=True)


class RecommendationsResponse(BaseModel):
    status: Literal["available", "insufficient_data"]
    message: str | None
    farms: list[FarmRecommendations]


class DashboardRecommendation(BaseModel):
    id: str
    recommendation_type: str = Field(serialization_alias="recommendationType")
    status: Literal["available", "needs_input"]
    summary: str
    decision_version: str = Field(serialization_alias="decisionVersion")
    decision: str

    model_config = ConfigDict(populate_by_name=True)
