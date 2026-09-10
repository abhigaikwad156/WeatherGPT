"""Farm and crop API schemas."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FarmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    area_hectares: Decimal | None = Field(default=None, gt=0, le=1_000_000)
    soil_type: str | None = Field(default=None, max_length=80)
    irrigation_type: str | None = Field(default=None, max_length=80)
    soil_moisture_percent: Decimal | None = Field(default=None, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())


class FarmUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    area_hectares: Decimal | None = Field(default=None, gt=0, le=1_000_000)
    soil_type: str | None = Field(default=None, max_length=80)
    irrigation_type: str | None = Field(default=None, max_length=80)
    soil_moisture_percent: Decimal | None = Field(default=None, ge=0, le=100)


class FarmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    latitude: Decimal
    longitude: Decimal
    area_hectares: Decimal | None
    soil_type: str | None
    irrigation_type: str | None
    soil_moisture_percent: Decimal | None


class CropCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    variety: str | None = Field(default=None, max_length=120)
    sowing_date: date | None = None
    growth_stage: str | None = Field(default=None, max_length=80)


class CropUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    variety: str | None = Field(default=None, max_length=120)
    sowing_date: date | None = None
    growth_stage: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class CropResponse(BaseModel):
    id: UUID
    farm_id: UUID
    name: str
    variety: str | None
    sowing_date: date | None
    growth_stage: str | None
    is_active: bool
