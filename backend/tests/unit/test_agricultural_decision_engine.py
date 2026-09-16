from datetime import UTC, datetime

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import (
    AgriculturalThresholds,
    CropProfile,
    IrrigationForecast,
    IrrigationProfile,
    IrrigationProfileSource,
    IrrigationSoilMoisture,
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
        soil_moisture=IrrigationSoilMoisture(sufficient_percent=60),
        forecast=IrrigationForecast(rainfall_lookahead_mm=10, horizon_days=3),
        source=IrrigationProfileSource(
            publisher="Test Agriculture Department",
            document_title="Test irrigation profile",
            source_uri="https://example.invalid/test-profile",
            reviewed_by="Test agronomist",
        ),
    )
    return IrrigationProfile(**{**base.__dict__, **changes})


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
    )
    return AgriculturalInputs(**{**base.__dict__, **changes})


def test_irrigation_waits_when_rainfall_is_expected() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs())[DecisionType.IRRIGATION]
    assert result.decision == DecisionValue.WAIT
    assert result.risk_level == RiskLevel.LOW
    assert result.deterministic is True
    assert result.ml_prediction is None
    assert result.llm_explanation is None


def test_irrigation_needs_input_when_no_matching_profile_exists() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(crop="onion"))[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.reasons == ("No matching crop-specific irrigation profile is configured",)


def test_irrigation_needs_input_when_matching_profile_has_null_threshold() -> None:
    unreviewed = irrigation_profile(
        forecast=IrrigationForecast(rainfall_lookahead_mm=None, horizon_days=3)
    )
    result = AgriculturalDecisionEngine(thresholds(profiles=(unreviewed,))).evaluate(inputs())[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.reasons == ("Matching irrigation profile has unreviewed threshold values",)


def test_irrigation_needs_input_when_soil_moisture_is_missing() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(inputs(soil_moisture_percent=None))[
        DecisionType.IRRIGATION
    ]

    assert result.decision == DecisionValue.NEEDS_INPUT
    assert result.reasons == ("Soil-moisture measurement is required for this irrigation profile",)


def test_irrigation_waits_when_soil_moisture_is_sufficient() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(soil_moisture_percent=60, forecast_rainfall_mm=0)
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.WAIT


def test_irrigation_applies_when_neither_profile_signal_is_sufficient() -> None:
    result = AgriculturalDecisionEngine(thresholds()).evaluate(
        inputs(soil_moisture_percent=40, forecast_rainfall_mm=0)
    )[DecisionType.IRRIGATION]

    assert result.decision == DecisionValue.APPLY


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
