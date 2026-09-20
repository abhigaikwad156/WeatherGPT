"""Schemas for authenticated device and farm location management."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CurrentLocationUpsert(BaseModel):
    """A location explicitly supplied by the browser after user consent."""

    latitude: Decimal = Field(description="GPS latitude, inclusive range -90 to 90", ge=-90, le=90)
    longitude: Decimal = Field(
        description="GPS longitude, inclusive range -180 to 180", ge=-180, le=180
    )
    accuracy_meters: Decimal | None = Field(
        default=None, description="Optional positive browser-reported accuracy in metres", gt=0
    )


class CurrentLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latitude: Decimal
    longitude: Decimal
    accuracy_meters: Decimal | None
    location_name: str | None
    city: str | None
    district: str | None
    state: str | None
    country: str | None
    country_code: str | None
    updated_at: datetime


class FarmLocationUpdate(BaseModel):
    """Permanent farm coordinates, optionally paired with user-provided display metadata."""

    latitude: Decimal = Field(description="Farm latitude, inclusive range -90 to 90", ge=-90, le=90)
    longitude: Decimal = Field(
        description="Farm longitude, inclusive range -180 to 180", ge=-180, le=180
    )
    accuracy_meters: Decimal | None = Field(
        default=None, description="Optional positive accuracy in metres", gt=0
    )
    location_name: str | None = Field(
        default=None,
        max_length=160,
        description=(
            "Optional user- or provider-supplied name; it is never inferred from coordinates"
        ),
    )

    @field_validator("location_name")
    @classmethod
    def normalize_location_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class FarmLocationResponse(BaseModel):
    latitude: Decimal
    longitude: Decimal
    accuracy_meters: Decimal | None
    location_name: str | None
    created_at: datetime
    updated_at: datetime
