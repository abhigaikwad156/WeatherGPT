"""Crop health report request and response schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CropHealthSymptom(StrEnum):
    LEAF_SPOTS = "leaf_spots"
    YELLOWING = "yellowing"
    WILTING = "wilting"
    WHITE_POWDER = "white_powder"
    LEAF_CURLING = "leaf_curling"
    LEAF_HOLES = "leaf_holes"
    STEM_DAMAGE = "stem_damage"
    FRUIT_DAMAGE = "fruit_damage"
    ROOT_ROT = "root_rot"
    STUNTED_GROWTH = "stunted_growth"
    OTHER = "other"


class CropHealthReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_id: UUID
    crop_id: UUID
    symptoms: list[CropHealthSymptom] = Field(min_length=1, max_length=11)
    duration_days: int = Field(ge=1, le=365)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CropHealthReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    farm_id: UUID
    farm_name: str
    crop_id: UUID
    crop_name: str
    symptoms: list[CropHealthSymptom]
    duration_days: int
    notes: str | None
    created_at: datetime
