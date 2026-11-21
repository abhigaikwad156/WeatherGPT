from datetime import UTC, datetime, timedelta

import pytest

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.irrigation import matching_irrigation_profile
from app.agriculture.thresholds import (
    AgriculturalThresholds,
    CropProfile,
    IrrigationForecast,
    IrrigationProfile,
    IrrigationProfileSource,
    IrrigationSchedule,
    IrrigationSoilMoisture,
    load_default_thresholds,
)
from app.agriculture.types import (
    AgriculturalInputs,
    DecisionType,
    DecisionValue,
    RiskLevel,
    WeatherSnapshot,
)


def irrigation_profile(**changes: object) -> IrrigationProfile:
    """Reviewed numeric values in this helper are test fixtures, not production guidance."""
    base = IrrigationProfile(
        crop="wheat",
        growth_stage="vegetative",
        soil_type="loam",
        irrigation_type="drip",
        region="Pune",
        soil_moisture=IrrigationSoilMoisture(
            sufficient_percent=60,
            measurement_basis="test sensor basis",
            sensor_depth_cm=30,
            maximum_age_hours=24,
        ),
        forecast=IrrigationForecast(rainfall_lookahead_mm=10, horizon_days=3),
        source=IrrigationProfileSource(
            publisher="Test Agriculture Department",
            document_title="Test irrigation profile",
            source_uri="https://example.invalid/test-profile",
            page_or_section="Test section",
            source_region="Pune",
            review_status="approved",
            reviewed_by="Test agronomist",
        ),
    )
    values = {**base.__dict__, **changes}
    if isinstance(values.get("schedule"), dict):
        values["schedule"] = IrrigationSchedule(**values["schedule"])
    return IrrigationProfile(**values)


def thresholds(*, profiles: tuple[IrrigationProfile, ...] | None = None) -> AgriculturalThresholds:
    return AgriculturalThresholds(
        irrigation_profiles=profiles if profiles is not None else (irrigation_profile(),),
        spray_rainfall_lookahead_mm=2,
        spray_min_humidity_percent=40,
        spray_max_humidity_percent=80,
        spray_max_wind_speed_kph=15,
        sowing_min_temperature_celsius=18,
        sowing_max_temperature_celsius=32,
        sowing_rainfall_min_mm=5,
        sowing_rainfall_max_mm=25,
        extreme_temperature_high_celsius=40,
        extreme_rainfall_mm=80,
        extreme_wind_speed_kph=45,
        crop_profiles={"wheat": CropProfile(12, 30)},
    )


def inputs(**changes: object) -> AgriculturalInputs:
    base = AgriculturalInputs(
        crop="wheat",
        growth_stage="vegetative",
        soil_type="loam",
        irrigation_type="drip",
        region="Pune",
        recent_rainfall_mm=4,
        forecast_rainfall_mm=12,
        temperature_celsius=24,
        humidity_percent=60,
        wind_speed_kph=8,
        soil_moisture_percent=40,
        soil_moisture_measured_at=datetime.now(UTC),
        soil_moisture_measurement_basis="test sensor basis",
        soil_moisture_sensor_depth_cm=30,
    )
    return AgriculturalInputs(**{**base.__dict__, **changes})


def test_irrigation_waits_when_rainfall_is_expected() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs())[DecisionType.IRRIGATION]
    assert result.decision == DecisionValue.DO_NOT_IRRIGATE
    assert result.risk_level == RiskLevel.LOW
    assert result.deterministic is True
    assert result.ml_prediction is None
    assert result.llm_explanation is None


def test_irrigation_needs_input_when_no_matching_profile_exists() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(crop="onion"))[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.reasons == (
        "No matching crop-, soil-, irrigation-, region-, and stage-specific profile is configured",
    )


def test_irrigation_needs_input_when_matching_profile_has_null_threshold() -> None:
    unreviewed = irrigation_profile(
        soil_moisture=IrrigationSoilMoisture(),
        forecast=IrrigationForecast(),
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(unreviewed,))).evaluate(inputs())[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == ["approved_irrigation_rule"]


def test_irrigation_needs_input_when_soil_moisture_is_missing() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(soil_moisture_percent=None, forecast_rainfall_mm=0)
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == [
        "soil_moisture_percent",
        "approved_irrigation_schedule",
    ]


def test_irrigation_waits_when_soil_moisture_is_sufficient() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(
            soil_moisture_percent=60,
            soil_moisture_measured_at=datetime.now(UTC),
            forecast_rainfall_mm=0,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.DO_NOT_IRRIGATE


def test_irrigation_applies_when_neither_profile_signal_is_sufficient() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(
            soil_moisture_percent=40,
            soil_moisture_measured_at=datetime.now(UTC),
            forecast_rainfall_mm=0,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.IRRIGATE


def test_sugarcane_profile_matches_crop_soil_method_stage_and_maharashtra() -> None:
    inputs_with_farm_data = inputs(
        crop="Sugarcane",
        crop_age_days=100,
        growth_stage="Tillering",
        soil_type="Black Soil",
        irrigation_type="Drip Irrigation",
        region="Pune, Maharashtra",
    )

    profile = matching_irrigation_profile(inputs_with_farm_data, load_default_thresholds())

    assert profile is not None
    assert profile.crop == "sugarcane"
    assert profile.growth_stage == "all_stages"
    decision = AgriculturalDecisionEngine().evaluate(inputs_with_farm_data)[DecisionType.IRRIGATION]
    assert decision.decision == DecisionValue.NEEDS_INPUT
    assert decision.metadata["applicable_crop_stage"] == "tillering"
    assert decision.metadata["source"]["publisher"] == "Tamil Nadu Agricultural University (TNAU)"
    assert "local_agronomist_review" in decision.metadata["missing_inputs"]
    assert "irrigation_layout" in decision.metadata["missing_inputs"]


def test_sugarcane_requires_crop_age_and_recorded_growth_stage() -> None:
    result = AgriculturalDecisionEngine().evaluate(
        inputs(
            crop="sugarcane",
            soil_type="Black Soil",
            irrigation_type="Drip Irrigation",
            region="Maharashtra",
            crop_age_days=None,
            growth_stage=None,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == ["crop_age_days", "growth_stage"]
    assert result.metadata["weather_limitations"] == [
        "Rainfall forecast is available but was not used because no matching reviewed rainfall "
        "rule was found."
    ]


def test_sugarcane_requires_region_before_profile_selection() -> None:
    result = AgriculturalDecisionEngine().evaluate(
        inputs(
            crop="sugarcane",
            crop_age_days=100,
            growth_stage="tillering",
            soil_type="Black Soil",
            irrigation_type="Drip Irrigation",
            region=None,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == ["region"]


def test_stage_specific_profile_does_not_match_when_stage_is_missing() -> None:
    profile = irrigation_profile(growth_stage="maturity")

    assert matching_irrigation_profile(
        inputs(growth_stage=None),
        thresholds(profiles=(profile,)),
    ) is None


def test_irrigation_needs_input_when_profile_weather_is_incomplete() -> None:
    profile = irrigation_profile(
        crop="sugarcane",
        growth_stage="tillering",
        soil_type="black soil",
        irrigation_type="drip",
        region="Maharashtra",
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(
        inputs(
            crop="sugarcane",
            crop_age_days=100,
            growth_stage="tillering",
            soil_type="Black Soil",
            irrigation_type="Drip Irrigation",
            region="Maharashtra",
            forecast_rainfall_mm=None,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.reasons == (
        "Complete, fresh forecast rainfall is required by this reviewed irrigation rule",
    )
    assert result.metadata["missing_inputs"] == ["forecast_rainfall_mm"]


def test_default_profile_requires_reviewed_thresholds_before_recommending_irrigation() -> None:
    profile = matching_irrigation_profile(
        inputs(
            crop="sugarcane",
            crop_age_days=100,
            growth_stage="grand growth",
            soil_type="Black Soil",
            irrigation_type="Drip Irrigation",
            region="Maharashtra",
        ),
        load_default_thresholds(),
    )

    assert profile is not None
    assert profile.forecast.rainfall_lookahead_mm is None
    assert profile.soil_moisture.sufficient_percent is None
    assert profile.schedule.interval_days == 3


@pytest.mark.parametrize(
    ("stage", "age"),
    (("tillering", 80), ("grand growth", 180), ("maturity", 300)),
)
def test_sugarcane_source_schedule_matches_recorded_growth_stages(stage: str, age: int) -> None:
    profile = irrigation_profile(
        crop="sugarcane",
        growth_stage=stage,
        soil_type="black soil",
        irrigation_type="drip",
        region="Maharashtra",
        irrigation_layout="paired_row",
        required_configuration={"emitter_flow_lph": {"min": 6, "max": 10}},
        forecast=IrrigationForecast(),
        schedule={"interval_days": 3, "trigger": "ET demand"},
    )
    farm_inputs = inputs(
        crop="sugarcane",
        growth_stage=stage,
        crop_age_days=age,
        soil_type="Black Soil",
        irrigation_type="Drip Irrigation",
        region="Pune, Maharashtra",
        irrigation_layout="paired_row",
        irrigation_configuration={"emitter_flow_lph": 8},
        soil_moisture_percent=None,
        last_irrigated_at=datetime.now(UTC).date() - timedelta(days=3),
        forecast_rainfall_mm=None,
    )

    result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(farm_inputs)[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.IRRIGATE
    assert result.metadata["applicable_crop_stage"] == stage
    assert result.metadata["data_basis"] == "source_schedule"
    assert result.metadata["weather_limitations"]
    assert result.explanations["en"].startswith("IRRIGATE:")
    assert result.explanations["mr"].startswith("सिंचन करा:")


def test_sugarcane_schedule_does_not_irrigate_before_interval() -> None:
    profile = irrigation_profile(
        crop="sugarcane",
        growth_stage="all_stages",
        soil_type="black soil",
        irrigation_type="drip",
        region="Maharashtra",
        irrigation_layout="paired_row",
        forecast=IrrigationForecast(),
        schedule={"interval_days": 3},
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(
        inputs(
            crop="sugarcane",
            growth_stage="maturity",
            crop_age_days=300,
            soil_type="Black Soil",
            irrigation_type="Drip",
            region="Maharashtra",
            irrigation_layout="paired_row",
            last_irrigated_at=datetime.now(UTC).date() - timedelta(days=2),
            soil_moisture_percent=None,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.DO_NOT_IRRIGATE


def test_available_rainfall_is_described_as_unused_without_a_reviewed_rule() -> None:
    profile = irrigation_profile(
        soil_moisture=IrrigationSoilMoisture(),
        forecast=IrrigationForecast(),
        schedule={"interval_days": 3},
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(
        inputs(
            soil_moisture_percent=None,
            forecast_rainfall_mm=12,
            last_irrigated_at=datetime.now(UTC).date() - timedelta(days=3),
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.IRRIGATE
    assert result.metadata["weather_limitations"] == [
        "Rainfall forecast is available but is not used because this profile has no reviewed "
        "rainfall rule."
    ]
    assert "पावसाचा अंदाज उपलब्ध आहे" in result.explanations["mr"]


def test_source_schedule_requires_recorded_irrigation_layout_and_configuration() -> None:
    profile = irrigation_profile(
        crop="sugarcane",
        growth_stage="all_stages",
        soil_type="black soil",
        irrigation_type="drip",
        region="Maharashtra",
        irrigation_layout="paired_row",
        required_configuration={"emitter_flow_lph": 8},
        schedule={"interval_days": 3},
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(
        inputs(
            crop="sugarcane",
            growth_stage="tillering",
            crop_age_days=80,
            soil_type="Black Soil",
            irrigation_type="Drip",
            region="Maharashtra",
            soil_moisture_percent=None,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == [
        "irrigation_layout",
        "irrigation_configuration.emitter_flow_lph",
    ]


def test_rainfall_threshold_defers_irrigation_when_sensor_is_below_threshold() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(soil_moisture_percent=40, forecast_rainfall_mm=10)
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.DO_NOT_IRRIGATE
    assert result.reasons[0].startswith("Forecast rainfall meets")


def test_unreviewed_and_expired_profiles_never_trigger_irrigation() -> None:
    base = irrigation_profile()
    unreviewed = IrrigationProfile(
        **{
            **base.__dict__,
            "source": IrrigationProfileSource(
                publisher="Test Agriculture Department",
                document_title="Test irrigation profile",
                source_uri="https://example.invalid/test-profile",
                page_or_section="Test section",
                source_region="Pune",
                review_status="supporting_only",
            ),
        }
    )
    expired = IrrigationProfile(
        **{
            **base.__dict__,
            "source": IrrigationProfileSource(
                publisher="Test Agriculture Department",
                document_title="Test irrigation profile",
                source_uri="https://example.invalid/test-profile",
                page_or_section="Test section",
                source_region="Pune",
                review_status="approved",
                reviewed_by="Test agronomist",
                effective_until=datetime.now(UTC).date() - timedelta(days=1),
            ),
        }
    )

    for profile, missing in (
        (unreviewed, "local_agronomist_review"),
        (expired, "reviewed_source"),
    ):
        result = AgriculturalDecisionEngine(thresholds(profiles=(profile,))).evaluate(
            inputs(soil_moisture_percent=30, forecast_rainfall_mm=0)
        )[DecisionType.IRRIGATION]
        assert result.decision == DecisionValue.NEEDS_INPUT
        assert result.metadata["missing_inputs"] == [missing]


def test_stale_soil_moisture_is_not_used() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(
            soil_moisture_percent=30,
            soil_moisture_measured_at=datetime.now(UTC) - timedelta(days=2),
            forecast_rainfall_mm=0,
        )
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.metadata["missing_inputs"] == [
        "fresh_soil_moisture_measurement",
        "approved_irrigation_schedule",
    ]


def test_spraying_waits_in_high_wind() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(wind_speed_kph=20))[
        DecisionType.SPRAYING
    ]
    assert result.decision == DecisionValue.WAIT
    assert result.risk_level == RiskLevel.HIGH


def test_sowing_window_is_suitable_when_conditions_match() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(forecast_rainfall_mm=10))[
        DecisionType.SOWING_WINDOW
    ]
    assert result.decision == DecisionValue.SUITABLE


def test_extreme_weather_detects_severe_forecast_signal() -> None:
    snapshot = WeatherSnapshot(datetime.now(UTC), severe_weather=True, condition="storm")
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(forecast_weather=(snapshot,))
    )[DecisionType.EXTREME_WEATHER]
    assert result.decision == DecisionValue.HIGH_RISK


def test_crop_compatibility_rejects_temperature_outside_profile() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(temperature_celsius=35))[
        DecisionType.CROP_WEATHER_COMPATIBILITY
    ]
    assert result.decision == DecisionValue.NOT_SUITABLE


def test_unconfigured_rules_do_not_apply_hidden_thresholds() -> None:
    result = AgriculturalDecisionEngine().evaluate(
        AgriculturalInputs(temperature_celsius=24, forecast_rainfall_mm=10)
    )
    assert result[DecisionType.IRRIGATION].decision == DecisionValue.NEEDS_INPUT
    assert result[DecisionType.SOWING_WINDOW].decision == DecisionValue.NEEDS_INPUT
