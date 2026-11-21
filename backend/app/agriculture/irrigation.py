"""Deterministic irrigation decisions from reviewed, source-linked profiles."""

from datetime import UTC, date, datetime
from typing import Any

from app.agriculture.thresholds import (
    AgriculturalThresholds,
    IrrigationProfile,
    IrrigationProfileSource,
)
from app.agriculture.types import (
    AgriculturalInputs,
    Decision,
    DecisionType,
    DecisionValue,
    RiskLevel,
)

_SUGARCANE_STAGES = {"germination", "tillering", "grand growth", "maturity"}


def recommend_irrigation(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> Decision:
    is_sugarcane = bool(inputs.crop and inputs.crop.strip().casefold() == "sugarcane")
    if is_sugarcane:
        missing: list[str] = []
        if inputs.crop_age_days is None or inputs.crop_age_days < 0:
            missing.append("crop_age_days")
        if not inputs.growth_stage:
            missing.append("growth_stage")
        elif _normalize_dimension(inputs.growth_stage) not in _SUGARCANE_STAGES:
            missing.append("growth_stage")
        for field in ("soil_type", "irrigation_type", "region"):
            if not getattr(inputs, field):
                missing.append(field)
        if missing:
            return _needs_input(
                "Sugarcane crop age, a recognized recorded growth stage, soil, irrigation "
                "method, and region are required before selecting a profile",
                missing,
                crop_age_days=inputs.crop_age_days,
                applicable_crop_stage=inputs.growth_stage,
                evidence=_evidence_for_crop(thresholds, inputs.crop),
                weather_limitations=_forecast_limitation_without_profile(inputs),
            )

    profile = matching_irrigation_profile(inputs, thresholds)
    if profile is None:
        missing_dimensions = [
            field
            for field in ("crop", "growth_stage", "soil_type", "irrigation_type", "region")
            if not getattr(inputs, field)
        ]
        return _needs_input(
            "No matching crop-, soil-, irrigation-, region-, and stage-specific profile "
            "is configured",
            missing_dimensions or ["approved_irrigation_profile"],
            crop_age_days=inputs.crop_age_days,
            applicable_crop_stage=inputs.growth_stage,
            evidence=_evidence_for_crop(thresholds, inputs.crop),
            weather_limitations=_forecast_limitation_without_profile(inputs),
        )

    metadata = _profile_metadata(profile, inputs)
    missing_configuration = _missing_configuration(profile, inputs)
    review_block = profile.review_block_reason(_evaluation_date(inputs))
    review_missing = {
        "source_expired": ["reviewed_source"],
        "source_not_yet_effective": ["effective_source_date"],
        "source_not_reviewed": ["local_agronomist_review"],
    }.get(review_block, [])
    if missing_configuration or review_missing:
        missing = missing_configuration + review_missing
        reason = (
            "The source schedule requires irrigation-system details that are not recorded "
            "and is not approved for this farm"
            if missing_configuration and review_missing
            else "The source schedule requires irrigation-system details that are not recorded"
            if missing_configuration
            else "The source is not approved for this farm's region and applicability conditions"
        )
        return _needs_input(
            reason,
            missing,
            profile,
            inputs,
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )

    moisture_rule = profile.soil_moisture
    soil_moisture = inputs.soil_moisture_percent
    moisture_missing: list[str] = []
    if moisture_rule.sufficient_percent is not None:
        if soil_moisture is None:
            moisture_missing.append("soil_moisture_percent")
        elif inputs.soil_moisture_measured_at is None:
            moisture_missing.append("soil_moisture_measured_at")
        elif not _measurement_is_fresh(inputs, moisture_rule.maximum_age_hours):
            moisture_missing.append("fresh_soil_moisture_measurement")
        elif (
            moisture_rule.measurement_basis is not None
            and inputs.soil_moisture_measurement_basis != moisture_rule.measurement_basis
        ):
            moisture_missing.append("soil_moisture_measurement_basis")
        elif (
            moisture_rule.sensor_depth_cm is not None
            and inputs.soil_moisture_sensor_depth_cm != moisture_rule.sensor_depth_cm
        ):
            moisture_missing.append("soil_moisture_sensor_depth_cm")

        if not moisture_missing and soil_moisture is not None:
            if soil_moisture >= moisture_rule.sufficient_percent:
                return _decision(
                    DecisionValue.DO_NOT_IRRIGATE,
                    RiskLevel.LOW,
                    0.9,
                    "Available soil moisture meets the reviewed profile's sufficiency threshold",
                    profile,
                    inputs,
                    data_basis="soil_moisture",
                    weather_limitations=_weather_limitations(profile, inputs),
                )

    rainfall_rule = profile.forecast
    if rainfall_rule.rainfall_lookahead_mm is not None:
        if inputs.forecast_rainfall_mm is None:
            return _needs_input(
                "Complete, fresh forecast rainfall is required by this reviewed irrigation rule",
                ["forecast_rainfall_mm"],
                profile,
                inputs,
                metadata=metadata,
                weather_limitations=_weather_limitations(profile, inputs),
            )
        if inputs.forecast_horizon_days != rainfall_rule.horizon_days:
            return _needs_input(
                "Forecast horizon does not match the reviewed irrigation rule",
                ["forecast_horizon_days"],
                profile,
                inputs,
                metadata=metadata,
                weather_limitations=_weather_limitations(profile, inputs),
            )
        if inputs.forecast_rainfall_mm >= rainfall_rule.rainfall_lookahead_mm:
            return _decision(
                DecisionValue.DO_NOT_IRRIGATE,
                RiskLevel.LOW,
                0.85,
                "Forecast rainfall meets the reviewed profile's irrigation deferral threshold",
                profile,
                inputs,
                data_basis="soil_moisture_and_forecast",
            )

    if moisture_rule.sufficient_percent is not None and not moisture_missing:
        return _decision(
            DecisionValue.IRRIGATE,
            RiskLevel.MEDIUM,
            0.75,
            "Measured soil moisture is below the reviewed profile threshold and no qualifying "
            "rainfall is forecast",
            profile,
            inputs,
            data_basis="soil_moisture"
            if rainfall_rule.rainfall_lookahead_mm is None
            else "soil_moisture_and_forecast",
            weather_limitations=_weather_limitations(profile, inputs),
        )

    if moisture_missing and profile.schedule.interval_days is None:
        return _needs_input(
            "No current usable soil-moisture reading is available and this profile has no "
            "approved fallback schedule",
            moisture_missing + ["approved_irrigation_schedule"],
            profile,
            inputs,
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )

    schedule = profile.schedule
    if schedule.interval_options_days:
        return _needs_input(
            "The source lists alternative irrigation intervals; a reviewer must select an "
            "applicable schedule",
            ["approved_schedule_interval_days"],
            profile,
            inputs,
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )
    if schedule.interval_days is None:
        return _needs_input(
            "The matching profile contains no approved soil-moisture threshold or irrigation "
            "schedule",
            ["approved_irrigation_rule"],
            profile,
            inputs,
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )
    if inputs.last_irrigated_at is None:
        return _needs_input(
            "The source-based schedule cannot be evaluated without the last irrigation date",
            ["last_irrigated_at"],
            profile,
            inputs,
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )
    days_since_irrigation = (_evaluation_date(inputs) - inputs.last_irrigated_at).days
    if days_since_irrigation < 0:
        return _needs_input(
            "The recorded last irrigation date is in the future",
            ["last_irrigated_at"],
            profile,
            inputs,
            metadata=metadata,
        )
    metadata["days_since_irrigation"] = days_since_irrigation
    metadata["schedule_interval_days"] = schedule.interval_days
    metadata["schedule_trigger"] = schedule.trigger
    if days_since_irrigation >= schedule.interval_days:
        return _decision(
            DecisionValue.IRRIGATE,
            RiskLevel.MEDIUM,
            0.7,
            f"The reviewed source schedule is due after {schedule.interval_days} days",
            profile,
            inputs,
            data_basis="source_schedule",
            metadata=metadata,
            weather_limitations=_weather_limitations(profile, inputs),
        )
    return _decision(
        DecisionValue.DO_NOT_IRRIGATE,
        RiskLevel.LOW,
        0.8,
        f"The last irrigation was {days_since_irrigation} days ago, before the reviewed "
        f"{schedule.interval_days}-day schedule interval",
        profile,
        inputs,
        data_basis="source_schedule",
        metadata=metadata,
        weather_limitations=_weather_limitations(profile, inputs),
    )


def matching_irrigation_profile(
    inputs: AgriculturalInputs, thresholds: AgriculturalThresholds
) -> IrrigationProfile | None:
    if not inputs.crop:
        return None
    matches = [profile for profile in thresholds.irrigation_profiles if _matches(profile, inputs)]
    if not matches:
        return None
    most_specific = max(profile.specificity() for profile in matches)
    candidates = [profile for profile in matches if profile.specificity() == most_specific]
    return candidates[0] if len(candidates) == 1 else None


def _matches(profile: IrrigationProfile, inputs: AgriculturalInputs) -> bool:
    return (
        profile.crop.casefold() == (inputs.crop or "").strip().casefold()
        and _matches_dimension(profile.growth_stage, inputs.growth_stage)
        and _matches_dimension(profile.soil_type, inputs.soil_type)
        and _matches_dimension(profile.irrigation_type, inputs.irrigation_type)
        and _matches_dimension(profile.region, inputs.region)
        and _matches_dimension(
            profile.irrigation_layout, inputs.irrigation_layout, allow_missing=True
        )
    )


def _matches_dimension(
    expected: str | None, actual: str | None, *, allow_missing: bool = False
) -> bool:
    if expected is None or _normalize_dimension(expected) == "all stages":
        return True
    if actual is None:
        return allow_missing
    if expected.casefold() == "maharashtra":
        return "maharashtra" in actual.casefold()
    return _normalize_dimension(expected) == _normalize_dimension(actual)


def _normalize_dimension(value: str) -> str:
    normalized = " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )
    if normalized.endswith(" irrigation"):
        normalized = normalized.removesuffix(" irrigation").strip()
    return normalized


def _missing_configuration(profile: IrrigationProfile, inputs: AgriculturalInputs) -> list[str]:
    missing: list[str] = []
    if profile.irrigation_layout and not inputs.irrigation_layout:
        missing.append("irrigation_layout")
    actual = inputs.irrigation_configuration or {}
    for key, expected in (profile.required_configuration or {}).items():
        value = actual.get(key)
        if value is None or not _configuration_value_matches(expected, value):
            missing.append(f"irrigation_configuration.{key}")
    return missing


def _configuration_value_matches(expected: Any, actual: object) -> bool:
    if isinstance(expected, dict) and {"min", "max"} <= expected.keys():
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and expected["min"] <= actual <= expected["max"]
        )
    return expected == actual


def _measurement_is_fresh(inputs: AgriculturalInputs, maximum_age_hours: float | None) -> bool:
    if inputs.soil_moisture_measured_at is None or maximum_age_hours is None:
        return False
    now = inputs.evaluation_time or datetime.now(UTC)
    measured_at = inputs.soil_moisture_measured_at
    if measured_at.tzinfo is None:
        return False
    age_hours = (now - measured_at).total_seconds() / 3600
    return 0 <= age_hours <= maximum_age_hours


def _evaluation_date(inputs: AgriculturalInputs) -> date:
    now = inputs.evaluation_time or datetime.now(UTC)
    return now.date()


def _profile_metadata(
    profile: IrrigationProfile,
    inputs: AgriculturalInputs,
) -> dict[str, Any]:
    stage_value = (
        inputs.growth_stage
        if profile.growth_stage and _normalize_dimension(profile.growth_stage) == "all stages"
        else profile.growth_stage or inputs.growth_stage
    )
    stage = _canonical_sugarcane_stage(stage_value)
    source = _source_mapping(profile.source)
    return {
        "source": source,
        "evidence": [
            {
                "claim": profile.source.evidence_claim,
                "applicable_crop_stage": stage,
                "irrigation_type": profile.irrigation_type,
                "source": source,
            }
        ]
        if profile.source.evidence_claim
        else [],
        "applicable_crop_stage": stage,
        "crop_age_days": inputs.crop_age_days,
        "source_review_status": profile.source.review_status,
        "source_schedule": {
            "interval_days": profile.schedule.interval_days,
            "interval_options_days": list(profile.schedule.interval_options_days),
            "trigger": profile.schedule.trigger,
        },
    }


def _canonical_sugarcane_stage(stage: str | None) -> str | None:
    if stage is None:
        return None
    normalized = _normalize_dimension(stage)
    return normalized if normalized in _SUGARCANE_STAGES else stage


def _source_mapping(source: IrrigationProfileSource) -> dict[str, object | None]:
    return {
        "publisher": source.publisher,
        "document_title": source.document_title,
        "source_uri": source.source_uri,
        "page_or_section": source.page_or_section,
        "source_region": source.source_region,
        "evidence_claim": source.evidence_claim,
        "review_status": source.review_status,
        "reviewed_by": source.reviewed_by,
        "effective_from": source.effective_from.isoformat() if source.effective_from else None,
        "effective_until": source.effective_until.isoformat() if source.effective_until else None,
    }


def _evidence_for_crop(
    thresholds: AgriculturalThresholds, crop: str | None
) -> list[dict[str, object]]:
    if not crop:
        return []
    return [
        {
            "claim": item.claim,
            "applicable_crop_stage": item.applicable_crop_stage,
            "irrigation_type": item.irrigation_type,
            "source": _source_mapping(item.source),
        }
        for item in thresholds.irrigation_evidence
        if item.crop.casefold() == crop.strip().casefold()
    ]


def _weather_limitations(profile: IrrigationProfile, inputs: AgriculturalInputs) -> list[str]:
    if inputs.forecast_rainfall_mm is None:
        return [
            "Rainfall forecast is unavailable; this decision could not account for forecast rain."
        ]
    if profile.forecast.rainfall_lookahead_mm is not None:
        return []
    return [
        "Rainfall forecast is available but is not used because this profile has no reviewed "
        "rainfall rule."
    ]


def _forecast_limitation_without_profile(inputs: AgriculturalInputs | None) -> list[str]:
    if inputs is not None and inputs.forecast_rainfall_mm is not None:
        return [
            "Rainfall forecast is available but was not used because no matching reviewed "
            "rainfall rule was found."
        ]
    return [
        "A complete rainfall forecast is unavailable; no rainfall-based irrigation rule was "
        "applied."
    ]


def _decision(
    value: DecisionValue,
    risk: RiskLevel,
    confidence: float,
    reason: str,
    profile: IrrigationProfile,
    inputs: AgriculturalInputs,
    *,
    data_basis: str,
    metadata: dict[str, Any] | None = None,
    weather_limitations: list[str] | None = None,
) -> Decision:
    details = metadata or _profile_metadata(profile, inputs)
    details["data_basis"] = data_basis
    details["weather_limitations"] = weather_limitations or []
    return Decision(
        DecisionType.IRRIGATION,
        value,
        risk,
        confidence,
        (reason,),
        metadata=details,
        explanations=_explanations(value, reason, [], weather_limitations or []),
    )


def _needs_input(
    reason: str,
    missing_inputs: list[str],
    profile: IrrigationProfile | None = None,
    inputs: AgriculturalInputs | None = None,
    *,
    crop_age_days: int | None = None,
    applicable_crop_stage: str | None = None,
    evidence: list[dict[str, object]] | None = None,
    metadata: dict[str, Any] | None = None,
    weather_limitations: list[str] | None = None,
) -> Decision:
    details = (
        metadata
        if metadata is not None
        else _profile_metadata(profile, inputs)
        if profile is not None and inputs is not None
        else {
            "source": None,
            "evidence": evidence or [],
            "applicable_crop_stage": applicable_crop_stage,
            "crop_age_days": crop_age_days,
        }
    )
    details["missing_inputs"] = missing_inputs
    if not details.get("weather_limitations"):
        details["weather_limitations"] = (
            weather_limitations
            if weather_limitations is not None
            else _forecast_limitation_without_profile(inputs)
        )
    details.setdefault("data_basis", "insufficient_data")
    return Decision(
        DecisionType.IRRIGATION,
        DecisionValue.NEEDS_INPUT,
        RiskLevel.UNKNOWN,
        0.0,
        (reason,),
        metadata=details,
        explanations=_explanations(
            DecisionValue.NEEDS_INPUT,
            reason,
            missing_inputs,
            details.get("weather_limitations", []),
        ),
    )


def _explanations(
    decision: DecisionValue,
    reason: str,
    missing_inputs: list[str],
    weather_limitations: list[str],
) -> dict[str, str]:
    decision_text_mr = {
        DecisionValue.IRRIGATE: "सिंचन करा",
        DecisionValue.DO_NOT_IRRIGATE: "आत्ता सिंचन करू नका",
        DecisionValue.NEEDS_INPUT: "अधिक माहिती आवश्यक",
    }.get(decision, decision.value)
    missing_labels = {
        "crop_age_days": "पेरणीची तारीख किंवा पिकाचे वय",
        "growth_stage": "नोंदवलेली वाढीची अवस्था",
        "soil_type": "मातीचा प्रकार",
        "irrigation_type": "सिंचन पद्धत",
        "region": "शेतीचा प्रदेश",
        "local_agronomist_review": "महाराष्ट्रातील कृषी तज्ज्ञांची पडताळणी",
        "irrigation_layout": "ड्रिप सिंचनाची मांडणी",
        "last_irrigated_at": "शेवटच्या सिंचनाची तारीख",
        "soil_moisture_percent": "मातीतील ओलाव्याचे मोजमाप",
        "soil_moisture_measured_at": "ओलावा मोजल्याची तारीख व वेळ",
        "soil_moisture_measurement_basis": "माती-ओलावा मोजण्याची पद्धत",
        "soil_moisture_sensor_depth_cm": "माती-ओलावा सेन्सरची खोली",
        "fresh_soil_moisture_measurement": "ताजे माती-ओलावा मोजमाप",
        "forecast_rainfall_mm": "पूर्ण पावसाचा अंदाज",
        "forecast_horizon_days": "पावसाच्या अंदाजाचा कालावधी",
        "approved_irrigation_profile": "लागू आणि पडताळलेला सिंचन नियम",
        "approved_irrigation_schedule": "पडताळलेले सिंचन वेळापत्रक",
        "approved_irrigation_rule": "पडताळलेला सिंचन नियम",
        "approved_schedule_interval_days": "पडताळलेले सिंचन अंतर",
        "reviewed_source": "पडताळलेला स्रोत",
        "effective_source_date": "स्रोत लागू होण्याची तारीख",
        "irrigation_configuration.lateral_diameter_mm": "ड्रिप लॅटरलचा व्यास",
        "irrigation_configuration.lateral_spacing_cm": "ड्रिप लॅटरलमधील अंतर",
        "irrigation_configuration.emitter_flow_lph": "ड्रिपरचा ताशी प्रवाह",
        "irrigation_configuration.emitter_spacing_cm": "ड्रिपरमधील अंतर",
        "irrigation_configuration.lateral_length_m": "ड्रिप लॅटरलची लांबी",
    }
    missing_en = ", ".join(item.replace("_", " ") for item in missing_inputs)
    missing_mr = ", ".join(
        missing_labels.get(item, item.replace("_", " ")) for item in missing_inputs
    )
    weather_en = " ".join(weather_limitations)
    english = f"{decision.value}: {reason}."
    marathi_reason = _marathi_reason(reason)
    marathi = f"{decision_text_mr}: {marathi_reason}."
    if missing_inputs:
        english += f" Missing: {missing_en}."
        marathi += f" आवश्यक माहिती: {missing_mr}."
    if weather_limitations:
        english += f" {weather_en}"
        if any("forecast is unavailable" in item.casefold() for item in weather_limitations):
            marathi += " पूर्ण पावसाचा अंदाज उपलब्ध नसल्याने त्याचा विचार करता आलेला नाही."
        elif any("forecast is available but" in item.casefold() for item in weather_limitations):
            marathi += (
                " पावसाचा अंदाज उपलब्ध आहे, पण लागू आणि पडताळलेला पावसाधारित नियम नसल्याने "
                "त्याचा वापर केलेला नाही."
            )
    return {"en": english, "mr": marathi}


def _marathi_reason(reason: str) -> str:
    if reason.startswith("Sugarcane crop age"):
        return "ऊसासाठी पीक वय, नोंदवलेली वाढीची अवस्था, माती, सिंचन पद्धत आणि प्रदेश आवश्यक आहेत"
    if reason.startswith("No matching crop-"):
        return "या पीक, माती, सिंचन पद्धत, प्रदेश आणि वाढीच्या अवस्थेसाठी पडताळलेला नियम उपलब्ध नाही"
    if reason.startswith("The source schedule requires"):
        return "स्रोताच्या वेळापत्रकासाठी सिंचन व्यवस्थेची काही माहिती नोंदवलेली नाही"
    if reason.startswith("The source is not approved"):
        return "हा स्रोत या प्रदेश आणि शेताच्या परिस्थितीसाठी अद्याप मंजूर झालेला नाही"
    if reason.startswith("Available soil moisture meets"):
        return "मातीतील उपलब्ध ओलावा पडताळलेल्या आवश्यक पातळीइतका किंवा त्यापेक्षा जास्त आहे"
    if reason.startswith("Complete, fresh forecast rainfall"):
        return "या पडताळलेल्या नियमासाठी पूर्ण आणि अद्ययावत पावसाचा अंदाज आवश्यक आहे"
    if reason.startswith("Forecast horizon"):
        return "पावसाच्या अंदाजाचा कालावधी पडताळलेल्या नियमाशी जुळत नाही"
    if reason.startswith("Forecast rainfall meets"):
        return "पावसाचा अंदाज पडताळलेल्या सिंचन पुढे ढकलण्याच्या मर्यादेइतका किंवा त्यापेक्षा जास्त आहे"
    if reason.startswith("Measured soil moisture is below"):
        return "मातीतील ओलावा पडताळलेल्या मर्यादेपेक्षा कमी आहे आणि पुरेसा पाऊस अपेक्षित नाही"
    if reason.startswith("No current usable soil-moisture"):
        return "मातीतील ओलाव्याचे ताजे मोजमाप उपलब्ध नाही आणि पडताळलेले पर्यायी वेळापत्रक नाही"
    if reason.startswith("The source lists alternative"):
        return "स्रोतामध्ये वेगवेगळे सिंचन अंतर दिले आहेत; योग्य पर्याय तज्ज्ञांनी निवडणे आवश्यक आहे"
    if reason.startswith("The matching profile contains no"):
        return "या प्रोफाइलमध्ये पडताळलेली ओलावा मर्यादा किंवा सिंचन वेळापत्रक नाही"
    if reason.startswith("The source-based schedule cannot"):
        return "स्रोताधारित वेळापत्रक तपासण्यासाठी शेवटच्या सिंचनाची तारीख आवश्यक आहे"
    if reason.startswith("The recorded last irrigation date is in the future"):
        return "शेवटच्या सिंचनाची नोंदलेली तारीख भविष्यातील आहे"
    if reason.startswith("The reviewed source schedule is due"):
        return "पडताळलेल्या स्रोताच्या वेळापत्रकानुसार सिंचनाची वेळ आली आहे"
    if reason.startswith("The last irrigation was"):
        return "शेवटच्या सिंचनानंतर पडताळलेल्या वेळापत्रकातील अंतर अद्याप पूर्ण झालेले नाही"
    return reason
