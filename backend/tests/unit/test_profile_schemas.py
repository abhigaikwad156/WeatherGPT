from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.farm import CropCreate, FarmCreate
from app.schemas.profile import FarmerProfileUpdate


def test_farm_schema_validates_coordinates_and_moisture() -> None:
    farm = FarmCreate(
        name="  Green   Valley Farm ",
        latitude=18.52,
        longitude=73.85,
        soil_moisture_percent=Decimal("42.5"),
    )

    assert farm.name == "Green Valley Farm"
    assert farm.soil_moisture_percent == Decimal("42.5")

    with pytest.raises(ValidationError):
        FarmCreate(name="Farm", latitude=91, longitude=73)
    with pytest.raises(ValidationError):
        FarmCreate(name="Farm", latitude=18, longitude=73, soil_moisture_percent=101)


def test_profile_and_crop_schema_validate_supported_values() -> None:
    profile = FarmerProfileUpdate(preferred_language="hi", preferred_units="imperial")
    crop = CropCreate(name="Wheat", variety="HD 2967", sowing_date=date(2026, 6, 1))

    assert profile.preferred_units == "imperial"
    assert crop.sowing_date == date(2026, 6, 1)

    with pytest.raises(ValidationError):
        FarmerProfileUpdate(preferred_units="unknown")
