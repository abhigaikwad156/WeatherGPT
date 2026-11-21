"""Read-only deterministic agricultural recommendation responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DecisionSource(BaseModel):
    publisher: str | None = None
    document_title: str | None = Field(default=None, serialization_alias="documentTitle")
    source_uri: str | None = Field(default=None, serialization_alias="sourceUri")
    page_or_section: str | None = Field(default=None, serialization_alias="pageOrSection")
    source_region: str | None = Field(default=None, serialization_alias="sourceRegion")
    review_status: str | None = Field(default=None, serialization_alias="reviewStatus")
    reviewed_by: str | None = Field(default=None, serialization_alias="reviewedBy")
    effective_from: str | None = Field(default=None, serialization_alias="effectiveFrom")
    effective_until: str | None = Field(default=None, serialization_alias="effectiveUntil")

    model_config = ConfigDict(populate_by_name=True)


class DecisionEvidence(BaseModel):
    claim: str
    applicable_crop_stage: str | None = Field(
        default=None, serialization_alias="applicableCropStage"
    )
    irrigation_type: str | None = Field(default=None, serialization_alias="irrigationType")
    source: DecisionSource

    model_config = ConfigDict(populate_by_name=True)


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
    applicable_crop_stage: str | None = Field(
        default=None, serialization_alias="applicableCropStage"
    )
    crop_age_days: int | None = Field(default=None, serialization_alias="cropAgeDays")
    source: DecisionSource | None = None
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    explanations: dict[str, str] = Field(default_factory=dict)
    data_basis: str | None = Field(default=None, serialization_alias="dataBasis")
    weather_limitations: list[str] = Field(
        default_factory=list, serialization_alias="weatherLimitations"
    )
    schedule_interval_days: int | None = Field(
        default=None, serialization_alias="scheduleIntervalDays"
    )
    missing_inputs: list[str] = Field(default_factory=list, serialization_alias="missingInputs")

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
    reasons: list[str] = Field(default_factory=list)
    applicable_crop_stage: str | None = Field(
        default=None, serialization_alias="applicableCropStage"
    )
    crop_age_days: int | None = Field(default=None, serialization_alias="cropAgeDays")
    source: DecisionSource | None = None
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    explanations: dict[str, str] = Field(default_factory=dict)
    data_basis: str | None = Field(default=None, serialization_alias="dataBasis")
    weather_limitations: list[str] = Field(
        default_factory=list, serialization_alias="weatherLimitations"
    )
    schedule_interval_days: int | None = Field(
        default=None, serialization_alias="scheduleIntervalDays"
    )
    missing_inputs: list[str] = Field(default_factory=list, serialization_alias="missingInputs")

    model_config = ConfigDict(populate_by_name=True)
