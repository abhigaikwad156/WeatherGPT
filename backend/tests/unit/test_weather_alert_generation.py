import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import AgriculturalThresholds
from app.domain.models import Farm, WeatherAlert
from app.weather import alerts as weather_alerts
from app.weather.types import HourlyWeather, NormalizedWeather, SevereWeather


class AlertResult:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def all(self) -> list[str]:
        return self.values


class AlertSession:
    def __init__(self) -> None:
        self.existing_alert_types: list[str] = []
        self.added: list[WeatherAlert] = []
        self.statement: object | None = None

    def scalars(self, statement: object) -> AlertResult:
        self.statement = statement
        return AlertResult(self.existing_alert_types)

    def add(self, alert: WeatherAlert) -> None:
        self.added.append(alert)


def make_farm(owner_id=None) -> Farm:
    return Farm(id=uuid4(), owner_id=owner_id or uuid4(), latitude=17, longitude=74, name="Farm")


def make_weather(farm_id, *, current=None, severe=(), fetched_at=None) -> NormalizedWeather:
    now = datetime.now(UTC)
    return NormalizedWeather(
        farm_id=farm_id,
        provider="test",
        fetched_at=fetched_at or now,
        current=current,
        hourly=(),
        daily=(),
        severe=severe,
    )


def use_high_temperature_rule(monkeypatch) -> None:
    monkeypatch.setattr(
        weather_alerts,
        "_get_decision_engine",
        lambda: AgriculturalDecisionEngine(
            AgriculturalThresholds(extreme_temperature_high_celsius=35)
        ),
    )


def test_generates_alert_when_configured_extreme_weather_rule_triggers(monkeypatch) -> None:
    use_high_temperature_rule(monkeypatch)
    farm = make_farm()
    session = AlertSession()
    now = datetime.now(UTC)
    weather = make_weather(
        farm.id,
        current=HourlyWeather(now, 40, None, None, None, None),
    )

    generated = weather_alerts.generate_weather_alerts(session, farm.owner_id, farm, weather)

    assert len(generated) == 1
    assert generated[0].user_id == farm.owner_id
    assert generated[0].farm_id == farm.id
    assert generated[0].title == "Extreme weather risk"
    assert "configured high-risk threshold" in generated[0].body
    assert generated[0].severity.value == "high"


def test_generates_severe_weather_alert_from_provider_signal(monkeypatch) -> None:
    monkeypatch.setattr(
        weather_alerts,
        "_get_decision_engine",
        lambda: AgriculturalDecisionEngine(AgriculturalThresholds()),
    )
    farm = make_farm()
    session = AlertSession()
    now = datetime.now(UTC)
    weather = make_weather(
        farm.id,
        severe=(SevereWeather("Provider warning", "Provider description", "high", now),),
    )

    generated = weather_alerts.generate_weather_alerts(session, farm.owner_id, farm, weather)

    assert len(generated) == 1
    assert generated[0].title == "Provider warning"
    assert generated[0].body == "Provider description"


@pytest.mark.parametrize(
    "weather_changes",
    [
        {"current": None},
        {
            "current": HourlyWeather(
                datetime.now(UTC) - timedelta(minutes=20), 40, None, None, None, None
            )
        },
        {"fetched_at": datetime.now(UTC) - timedelta(hours=1)},
    ],
)
def test_does_not_generate_when_required_weather_data_is_missing_or_stale(
    monkeypatch, weather_changes
) -> None:
    use_high_temperature_rule(monkeypatch)
    farm = make_farm()
    session = AlertSession()
    changes = {
        "current": HourlyWeather(datetime.now(UTC), 40, None, None, None, None),
        **weather_changes,
    }
    weather = make_weather(farm.id, **changes)

    generated = weather_alerts.generate_weather_alerts(session, farm.owner_id, farm, weather)

    assert generated == []
    assert session.added == []


def test_does_not_generate_for_a_farm_owned_by_another_user(monkeypatch) -> None:
    use_high_temperature_rule(monkeypatch)
    farm = make_farm()
    weather = make_weather(
        farm.id,
        current=HourlyWeather(datetime.now(UTC), 40, None, None, None, None),
    )
    session = AlertSession()

    with pytest.raises(ValueError, match="farm owner"):
        weather_alerts.generate_weather_alerts(session, uuid4(), farm, weather)

    assert session.added == []


def test_does_not_duplicate_the_same_active_condition(monkeypatch) -> None:
    use_high_temperature_rule(monkeypatch)
    farm = make_farm()
    session = AlertSession()
    weather = make_weather(
        farm.id,
        current=HourlyWeather(datetime.now(UTC), 40, None, None, None, None),
    )

    first = weather_alerts.generate_weather_alerts(session, farm.owner_id, farm, weather)
    session.existing_alert_types.extend(alert.alert_type for alert in first)
    second = weather_alerts.generate_weather_alerts(session, farm.owner_id, farm, weather)

    assert len(first) == 1
    assert second == []
    assert len(session.added) == 1
    statement = str(session.statement)
    assert "weather_alerts.user_id" in statement
    assert "weather_alerts.farm_id" in statement


def test_weather_service_generates_alerts_when_using_cached_weather(monkeypatch) -> None:
    from app.weather import service as weather_service

    farm = make_farm()
    weather = make_weather(farm.id)
    calls: list[tuple[object, ...]] = []

    class Cache:
        def get(self, _farm_id):
            return weather

    class Provider:
        def fetch(self, *_args):
            raise AssertionError("cached weather should not fetch again")

    monkeypatch.setattr(
        weather_service,
        "generate_weather_alerts",
        lambda *args: calls.append(args),
    )

    service = weather_service.WeatherService(AlertSession(), Provider(), Cache())
    result = service.get_weather(farm)
    repeated_result = service.get_weather(farm)

    assert result is weather
    assert repeated_result is weather
    assert len(calls) == 2
    assert calls[0][1:3] == (farm.owner_id, farm)


def test_reuses_engine_for_unchanged_threshold_file(tmp_path, monkeypatch) -> None:
    config = tmp_path / "thresholds.json"
    config.write_text(
        '{"extreme_temperature_high_celsius":35,'
        '"source_notes":{"extreme_temperature_high_celsius":"test rule"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        weather_alerts.get_settings(),
        "agricultural_thresholds_path",
        config,
    )
    weather_alerts._decision_engine_for_config.cache_clear()

    first = weather_alerts._get_decision_engine()
    second = weather_alerts._get_decision_engine()

    assert first is second


def test_reloads_engine_when_threshold_file_changes(tmp_path, monkeypatch) -> None:
    config = tmp_path / "thresholds.json"
    initial = (
        '{"extreme_temperature_high_celsius":35,'
        '"source_notes":{"extreme_temperature_high_celsius":"test rule"}}'
    )
    updated = (
        '{"extreme_temperature_high_celsius":36,'
        '"source_notes":{"extreme_temperature_high_celsius":"test rule"}}'
    )
    config.write_text(initial, encoding="utf-8")
    monkeypatch.setattr(
        weather_alerts.get_settings(),
        "agricultural_thresholds_path",
        config,
    )
    weather_alerts._decision_engine_for_config.cache_clear()

    first = weather_alerts._get_decision_engine()
    previous_stat = config.stat()
    config.write_text(updated, encoding="utf-8")
    os.utime(config, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns + 1_000_000))

    second = weather_alerts._get_decision_engine()

    assert second is not first
    assert second.thresholds.extreme_temperature_high_celsius == 36


@pytest.mark.parametrize(
    ("contents", "exception"),
    [
        ("{invalid json", ValueError),
        (
            '{"extreme_temperature_high_celsius":35}',
            ValueError,
        ),
    ],
)
def test_invalid_threshold_configuration_is_not_cached(
    tmp_path, monkeypatch, contents, exception
) -> None:
    config = tmp_path / "thresholds.json"
    config.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        weather_alerts.get_settings(),
        "agricultural_thresholds_path",
        config,
    )
    weather_alerts._decision_engine_for_config.cache_clear()

    with pytest.raises(exception):
        weather_alerts._get_decision_engine()

    assert weather_alerts._decision_engine_for_config.cache_info().currsize == 0


def test_missing_threshold_configuration_is_not_cached(tmp_path, monkeypatch) -> None:
    config = tmp_path / "missing-thresholds.json"
    monkeypatch.setattr(
        weather_alerts.get_settings(),
        "agricultural_thresholds_path",
        config,
    )
    weather_alerts._decision_engine_for_config.cache_clear()

    with pytest.raises(FileNotFoundError):
        weather_alerts._get_decision_engine()

    assert weather_alerts._decision_engine_for_config.cache_info().currsize == 0


def test_only_extreme_weather_rule_is_evaluated(monkeypatch) -> None:
    use_high_temperature_rule(monkeypatch)
    farm = make_farm()
    weather = make_weather(
        farm.id,
        current=HourlyWeather(datetime.now(UTC), 40, None, None, None, None),
    )
    calls = []
    original = weather_alerts.assess_extreme_weather

    def record_assessment(inputs, thresholds):
        calls.append(inputs)
        return original(inputs, thresholds)

    monkeypatch.setattr(weather_alerts, "assess_extreme_weather", record_assessment)
    weather_alerts.generate_weather_alerts(AlertSession(), farm.owner_id, farm, weather)

    assert len(calls) == 1
