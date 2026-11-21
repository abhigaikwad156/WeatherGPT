import ast
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, Index, inspect

from app.domain.models import Farm, FarmerCrop, User, UserCurrentLocation
from app.infrastructure.database import Base


def _migration_columns(table_name: str) -> set[str]:
    migration_directory = Path(__file__).parents[2] / "alembic" / "versions"
    columns: set[str] = set()
    for migration_file in migration_directory.glob("*.py"):
        tree = ast.parse(migration_file.read_text(encoding="utf-8"))
        timestamp_columns = {
            argument.args[0].value
            for definition in ast.walk(tree)
            if isinstance(definition, ast.FunctionDef)
            and definition.name == "timestamp_columns"
            for argument in ast.walk(definition)
            if isinstance(argument, ast.Call)
            and isinstance(argument.func, ast.Attribute)
            and argument.func.attr == "Column"
            and argument.args
            and isinstance(argument.args[0], ast.Constant)
            and isinstance(argument.args[0].value, str)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != table_name:
                continue
            if node.func.attr == "create_table":
                column_arguments = node.args[1:]
            elif node.func.attr == "add_column" and len(node.args) > 1:
                column_arguments = node.args[1:2]
            else:
                continue
            for argument in column_arguments:
                if (
                    isinstance(argument, ast.Starred)
                    and isinstance(argument.value, ast.Call)
                    and isinstance(argument.value.func, ast.Name)
                    and argument.value.func.id == "timestamp_columns"
                ):
                    columns.update(timestamp_columns)
                    continue
                if (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Attribute)
                    and argument.func.attr == "Column"
                    and argument.args
                    and isinstance(argument.args[0], ast.Constant)
                    and isinstance(argument.args[0].value, str)
                ):
                    columns.add(argument.args[0].value)
    return columns


@pytest.mark.parametrize(("table_name", "model"), [("farms", Farm), ("farmer_crops", FarmerCrop)])
def test_farm_related_model_columns_are_created_by_migrations(
    table_name: str, model: type[Farm] | type[FarmerCrop]
) -> None:
    assert _migration_columns(table_name) == set(model.__table__.columns.keys())


def test_deployment_startup_applies_migrations_before_serving() -> None:
    backend_directory = Path(__file__).parents[2]
    startup_configs = (
        backend_directory / "Dockerfile",
        backend_directory.parents[0] / "render.yaml",
    )

    for path in startup_configs:
        assert "alembic upgrade head && exec uvicorn" in path.read_text(encoding="utf-8")


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
