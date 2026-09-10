"""Farmer profile schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class FarmerProfileUpdate(BaseModel):
    preferred_language: str | None = Field(default=None, min_length=2, max_length=10)
    location: str | None = Field(default=None, max_length=160)
    preferred_units: str | None = Field(default=None, pattern="^(metric|imperial)$")


class FarmerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    preferred_language: str
    location: str | None
    preferred_units: str
