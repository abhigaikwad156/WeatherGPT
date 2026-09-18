from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint, Index, inspect

from app.domain.models import Farm, User, UserCurrentLocation
from app.infrastructure.database import Base


def test_all_expected_domain_tables_are_registered() -> None:
    assert {
        "users",
        "user_current_locations",
        "farms",
        "crops",
        "farmer_crops",
        "weather_observations",
        "weather_forecasts",
        "weather_alerts",
        "recommendations",
        "conversations",
        "messages",
    }.issubset(Base.metadata.tables)


def test_user_normalizes_and_validates_email() -> None:
    user = User(email=" FARMER@example.COM ", password_hash="hash", display_name="Farmer")

    assert user.email == "farmer@example.com"
    with pytest.raises(ValueError, match="valid email"):
        User(email="invalid-email", password_hash="hash", display_name="Farmer")


def test_farm_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValueError, match="latitude"):
        Farm(name="Test farm", latitude=Decimal("91"), longitude=Decimal("73"))
    with pytest.raises(ValueError, match="longitude"):
        Farm(name="Test farm", latitude=Decimal("18"), longitude=Decimal("181"))


def test_farm_has_coordinate_constraints_and_spatial_index() -> None:
    constraints = {
        constraint.name
        for constraint in Farm.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    indexes = {index.name for index in Farm.__table__.indexes if isinstance(index, Index)}

    assert {
        "ck_farms_latitude_range",
        "ck_farms_longitude_range",
        "ck_farms_location_accuracy_positive",
    }.issubset(constraints)
    assert "ix_farms_location" in indexes


def test_current_location_has_coordinate_and_accuracy_constraints() -> None:
    constraints = {
        constraint.name
        for constraint in UserCurrentLocation.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {
        "ck_user_current_locations_latitude_range",
        "ck_user_current_locations_longitude_range",
        "ck_user_current_locations_accuracy_positive",
    }.issubset(constraints)


def test_core_relationships_are_configured() -> None:
    user_relationships = set(inspect(User).relationships.keys())
    farm_relationships = set(inspect(Farm).relationships.keys())

    assert {"farms", "farmer_crops", "conversations"}.issubset(user_relationships)
    assert {"owner", "weather_observations", "weather_forecasts"}.issubset(farm_relationships)
