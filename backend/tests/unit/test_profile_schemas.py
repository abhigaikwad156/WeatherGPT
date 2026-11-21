from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.models import Farm
from app.schemas.farm import CropCreate, FarmCreate, FarmUpdate
from app.schemas.profile import FarmerProfileUpdate
from app.services.profiles import update_farm


def test_farm_schema_validates_coordinates_and_moisture() -> None:
    farm = FarmCreate(
        name="  Green   Valley Farm ",
        latitude=18.52,
        longitude=73.85,
        region="  Pune,   Maharashtra ",
        soil_moisture_percent=Decimal("42.5"),
        soil_moisture_measured_at=datetime(2026, 6, 1, tzinfo=UTC),
        irrigation_layout="paired_row",
        irrigation_configuration={"emitter_flow_lph": 8},
        location_name="  Example   Village, Maharashtra  ",
    )

    assert farm.name == "Green Valley Farm"
    assert farm.soil_moisture_percent == Decimal("42.5")
    assert farm.region == "Pune, Maharashtra"
    assert farm.irrigation_layout == "paired_row"
    assert farm.irrigation_configuration == {"emitter_flow_lph": 8.0}
    assert farm.location_name == "Example Village, Maharashtra"

    with pytest.raises(ValidationError):
        FarmCreate(name="Farm", latitude=91, longitude=73)
    with pytest.raises(ValidationError):
        FarmCreate(name="Farm", latitude=18, longitude=73, soil_moisture_percent=101)


def test_profile_and_crop_schema_validate_supported_values() -> None:
    profile = FarmerProfileUpdate(preferred_language="hi", preferred_units="imperial")
    crop = CropCreate(
        name="Wheat",
        variety="HD 2967",
        sowing_date=date(2026, 6, 1),
        last_irrigated_at=date(2026, 6, 10),
    )

    assert profile.preferred_units == "imperial"
    assert crop.sowing_date == date(2026, 6, 1)
    assert crop.last_irrigated_at == date(2026, 6, 10)

    with pytest.raises(ValidationError):
        FarmerProfileUpdate(preferred_units="unknown")


def test_farm_update_normalizes_region_and_invalidates_old_moisture_timestamp() -> None:
    farm = Farm(
        region="Old region",
        soil_moisture_percent=Decimal("40"),
        soil_moisture_measured_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    update_farm(
        farm,
        FarmUpdate(region="  Satara,   Maharashtra ", soil_moisture_percent=Decimal("42")),
    )

    assert farm.region == "Satara, Maharashtra"
    assert farm.soil_moisture_percent == Decimal("42")
    assert farm.soil_moisture_measured_at is None
