"""Create WeatherGPT domain tables.

Revision ID: 20260910_0002
Revises: 20260910_0001
Create Date: 2026-09-10
"""

import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260910_0002"
down_revision: str | None = "20260910_0001"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE TYPE alert_severity AS ENUM ('low', 'medium', 'high', 'critical')")
    op.execute(
        "CREATE TYPE recommendation_status AS ENUM ('available', 'needs_input', 'not_available')"
    )
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")
    alert_severity = postgresql.ENUM(name="alert_severity", create_type=False)
    recommendation_status = postgresql.ENUM(name="recommendation_status", create_type=False)
    message_role = postgresql.ENUM(name="message_role", create_type=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("preferred_language", sa.String(length=10), server_default="mr", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint("char_length(trim(email)) > 3", name="ck_users_email_not_blank"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "farms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("latitude", sa.Numeric(8, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column(
            "location",
            Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("area_hectares", sa.Numeric(10, 2)),
        *timestamp_columns(),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_farms_latitude_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_farms_longitude_range"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_farms_owner_id", "farms", ["owner_id"])
    op.create_index("ix_farms_location", "farms", ["location"], postgresql_using="gist")

    op.create_table(
        "crops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scientific_name", sa.String(length=160)),
        *timestamp_columns(),
        sa.UniqueConstraint("name", name="uq_crops_name"),
    )
    op.create_index("ix_crops_name", "crops", ["name"])

    op.create_table(
        "farmer_crops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variety", sa.String(length=120)),
        sa.Column("growth_stage", sa.String(length=80)),
        sa.Column("planted_at", sa.Date()),
        sa.Column("harvested_at", sa.Date()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "harvested_at IS NULL OR planted_at IS NULL OR harvested_at >= planted_at",
            name="ck_farmer_crops_dates",
        ),
        sa.ForeignKeyConstraint(["farmer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], ondelete="RESTRICT"),
    )
    for column in ("farmer_id", "farm_id", "crop_id"):
        op.create_index(f"ix_farmer_crops_{column}", "farmer_crops", [column])

    op.create_table(
        "weather_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("temperature_celsius", sa.Numeric(5, 2)),
        sa.Column("humidity_percent", sa.Numeric(5, 2)),
        sa.Column("rainfall_mm", sa.Numeric(7, 2)),
        sa.Column("wind_speed_kph", sa.Numeric(6, 2)),
        *timestamp_columns(),
        sa.CheckConstraint(
            "humidity_percent IS NULL OR humidity_percent BETWEEN 0 AND 100",
            name="ck_weather_observations_humidity_range",
        ),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "farm_id", "observed_at", "provider", name="uq_weather_observations_source"
        ),
    )
    op.create_index("ix_weather_observations_farm_id", "weather_observations", ["farm_id"])
    op.create_index("ix_weather_observations_observed_at", "weather_observations", ["observed_at"])

    op.create_table(
        "weather_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("temperature_min_celsius", sa.Numeric(5, 2)),
        sa.Column("temperature_max_celsius", sa.Numeric(5, 2)),
        sa.Column("precipitation_mm", sa.Numeric(7, 2)),
        sa.Column("rain_probability_percent", sa.Numeric(5, 2)),
        *timestamp_columns(),
        sa.CheckConstraint(
            "rain_probability_percent IS NULL OR rain_probability_percent BETWEEN 0 AND 100",
            name="ck_weather_forecasts_rain_probability_range",
        ),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "farm_id", "forecast_for", "issued_at", "provider", name="uq_weather_forecasts_source"
        ),
    )
    op.create_index("ix_weather_forecasts_farm_id", "weather_forecasts", ["farm_id"])
    op.create_index("ix_weather_forecasts_forecast_for", "weather_forecasts", ["forecast_for"])

    _create_alert_recommendation_conversation_tables(
        alert_severity, recommendation_status, message_role
    )


def _create_alert_recommendation_conversation_tables(
    alert_severity: postgresql.ENUM,
    recommendation_status: postgresql.ENUM,
    message_role: postgresql.ENUM,
) -> None:
    op.create_table(
        "weather_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_crop_id", postgresql.UUID(as_uuid=True)),
        sa.Column("alert_type", sa.String(length=80), nullable=False),
        sa.Column("severity", alert_severity, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farmer_crop_id"], ["farmer_crops.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_crop_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recommendation_type", sa.String(length=80), nullable=False),
        sa.Column("status", recommendation_status, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("decision_version", sa.String(length=80), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farmer_crop_id"], ["farmer_crops.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True)),
        sa.Column("language", sa.String(length=10), server_default="mr", nullable=False),
        sa.Column("title", sa.String(length=200)),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True)),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
    )
    for table, columns in {
        "weather_alerts": ("user_id", "farm_id", "farmer_crop_id"),
        "recommendations": ("user_id", "farm_id", "farmer_crop_id"),
        "conversations": ("user_id", "farm_id"),
        "messages": ("conversation_id", "sender_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "messages",
        "conversations",
        "recommendations",
        "weather_alerts",
        "weather_forecasts",
        "weather_observations",
        "farmer_crops",
        "crops",
        "farms",
        "users",
    ):
        op.drop_table(table)
    for enum_name in ("message_role", "recommendation_status", "alert_severity"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    op.execute("DROP EXTENSION IF EXISTS postgis")
