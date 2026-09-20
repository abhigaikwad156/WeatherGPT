"""SQLAlchemy domain models for WeatherGPT's persistent data."""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum, StrEnum

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.infrastructure.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationStatus(StrEnum):
    AVAILABLE = "available"
    NEEDS_INPUT = "needs_input"
    NOT_AVAILABLE = "not_available"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(trim(email)) > 3", name="ck_users_email_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(10), default="mr", nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    preferred_units: Mapped[str] = mapped_column(String(20), default="metric", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    farms: Mapped[list["Farm"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    farmer_crops: Mapped[list["FarmerCrop"]] = relationship(back_populates="farmer")
    weather_alerts: Mapped[list["WeatherAlert"]] = relationship(back_populates="user")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    messages: Mapped[list["Message"]] = relationship(back_populates="sender")
    current_device_location: Mapped["UserCurrentLocation | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @validates("email")
    def validate_email(self, _: str, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email must be a valid email address")
        return normalized


class UserCurrentLocation(TimestampMixin, Base):
    """The most recently submitted device location for one authenticated user."""

    __tablename__ = "user_current_locations"
    __table_args__ = (
        CheckConstraint(
            "latitude BETWEEN -90 AND 90", name="ck_user_current_locations_latitude_range"
        ),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_user_current_locations_longitude_range"
        ),
        CheckConstraint(
            "accuracy_meters IS NULL OR accuracy_meters > 0",
            name="ck_user_current_locations_accuracy_positive",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    location_name: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))

    user: Mapped[User] = relationship(back_populates="current_device_location")


class Farm(TimestampMixin, Base):
    __tablename__ = "farms"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_farms_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_farms_longitude_range"),
        CheckConstraint(
            "soil_moisture_percent IS NULL OR soil_moisture_percent BETWEEN 0 AND 100",
            name="ck_farms_soil_moisture_range",
        ),
        CheckConstraint(
            "location_accuracy_meters IS NULL OR location_accuracy_meters > 0",
            name="ck_farms_location_accuracy_positive",
        ),
        Index("ix_farms_location", "location", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    location: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    location_name: Mapped[str | None] = mapped_column(String(160))
    location_accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    area_hectares: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    soil_type: Mapped[str | None] = mapped_column(String(80))
    irrigation_type: Mapped[str | None] = mapped_column(String(80))
    soil_moisture_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    owner: Mapped[User] = relationship(back_populates="farms")
    farmer_crops: Mapped[list["FarmerCrop"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan"
    )
    weather_observations: Mapped[list["WeatherObservation"]] = relationship(back_populates="farm")
    weather_forecasts: Mapped[list["WeatherForecast"]] = relationship(back_populates="farm")
    weather_alerts: Mapped[list["WeatherAlert"]] = relationship(back_populates="farm")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="farm")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="farm")

    @validates("latitude", "longitude")
    def validate_coordinates(self, key: str, value: Decimal) -> Decimal:
        coordinate = Decimal(value)
        lower, upper = (-90, 90) if key == "latitude" else (-180, 180)
        if not lower <= coordinate <= upper:
            raise ValueError(f"{key} is outside its valid geographic range")
        return coordinate


class Crop(TimestampMixin, Base):
    __tablename__ = "crops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(160))

    farmer_crops: Mapped[list["FarmerCrop"]] = relationship(back_populates="crop")


class FarmerCrop(TimestampMixin, Base):
    __tablename__ = "farmer_crops"
    __table_args__ = (
        CheckConstraint(
            "harvested_at IS NULL OR planted_at IS NULL OR harvested_at >= planted_at",
            name="ck_farmer_crops_dates",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    crop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crops.id", ondelete="RESTRICT"), index=True
    )
    variety: Mapped[str | None] = mapped_column(String(120))
    growth_stage: Mapped[str | None] = mapped_column(String(80))
    planted_at: Mapped[date | None] = mapped_column(Date())
    harvested_at: Mapped[date | None] = mapped_column(Date())
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    farmer: Mapped[User] = relationship(back_populates="farmer_crops")
    farm: Mapped[Farm] = relationship(back_populates="farmer_crops")
    crop: Mapped[Crop] = relationship(back_populates="farmer_crops")
    weather_alerts: Mapped[list["WeatherAlert"]] = relationship(back_populates="farmer_crop")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="farmer_crop")


class WeatherObservation(TimestampMixin, Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint(
            "farm_id", "observed_at", "provider", name="uq_weather_observations_source"
        ),
        CheckConstraint(
            "humidity_percent IS NULL OR humidity_percent BETWEEN 0 AND 100",
            name="ck_weather_observations_humidity_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(120))
    temperature_celsius: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rainfall_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    wind_speed_kph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    farm: Mapped[Farm] = relationship(back_populates="weather_observations")


class WeatherForecast(TimestampMixin, Base):
    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "farm_id", "forecast_for", "issued_at", "provider", name="uq_weather_forecasts_source"
        ),
        CheckConstraint(
            "rain_probability_percent IS NULL OR rain_probability_percent BETWEEN 0 AND 100",
            name="ck_weather_forecasts_rain_probability_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    forecast_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(120))
    temperature_min_celsius: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    temperature_max_celsius: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    rain_probability_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    farm: Mapped[Farm] = relationship(back_populates="weather_forecasts")


class WeatherAlert(TimestampMixin, Base):
    __tablename__ = "weather_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    farmer_crop_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farmer_crops.id", ondelete="SET NULL"), index=True
    )
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        SqlEnum(AlertSeverity, name="alert_severity", values_callable=enum_values), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="weather_alerts")
    farm: Mapped[Farm] = relationship(back_populates="weather_alerts")
    farmer_crop: Mapped[FarmerCrop | None] = relationship(back_populates="weather_alerts")


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True
    )
    farmer_crop_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farmer_crops.id", ondelete="SET NULL"), index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        SqlEnum(RecommendationStatus, name="recommendation_status", values_callable=enum_values),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB())
    decision_version: Mapped[str] = mapped_column(String(80), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="recommendations")
    farm: Mapped[Farm] = relationship(back_populates="recommendations")
    farmer_crop: Mapped[FarmerCrop | None] = relationship(back_populates="recommendations")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    farm_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farms.id", ondelete="SET NULL"), index=True
    )
    language: Mapped[str] = mapped_column(String(10), default="mr", nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="conversations")
    farm: Mapped[Farm | None] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        SqlEnum(MessageRole, name="message_role", values_callable=enum_values), nullable=False
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sender: Mapped[User | None] = relationship(back_populates="messages")
