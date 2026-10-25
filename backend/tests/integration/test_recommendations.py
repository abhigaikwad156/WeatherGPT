from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agriculture.engine import AgriculturalDecisionEngine
from app.agriculture.thresholds import AgriculturalThresholds
from app.api.dependencies import get_current_user, get_db_session
from app.domain.models import Crop, Farm, FarmerCrop, User
from app.main import create_app
from app.weather.providers import WeatherProviderError
from app.weather.types import DailyWeather, HourlyWeather, NormalizedWeather, SevereWeather


class Result:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class RecommendationSession:
    def __init__(
        self, user_id, farms: list[Farm], crops: list[FarmerCrop]
    ) -> None:
        self.user_id = user_id
        self.farms = farms
        self.crops = crops
        self.statements: list[str] = []
        self.committed = False

    def scalars(self, statement: object) -> Result:
        self.statements.append(str(statement))
        entity = statement.column_descriptions[0]["entity"]
        if entity is Farm:
            return Result([farm for farm in self.farms if farm.owner_id == self.user_id])
        return Result(
            [
                crop
                for crop in self.crops
                if crop.farmer_id == self.user_id
                and any(
                    farm.id == crop.farm_id
                    for farm in self.farms
                    if farm.owner_id == self.user_id
                )
                and crop.is_active
            ]
        )

    def commit(self) -> None:
        self.committed = True


def _farm(owner_id) -> Farm:
    return Farm(
        id=uuid4(),
        owner_id=owner_id,
        name="Owned farm",
        latitude=Decimal("18.5"),
        longitude=Decimal("73.8"),
        location="POINT(73.8 18.5)",
    )


def _crop(user_id, farm: Farm) -> FarmerCrop:
    crop = Crop(id=uuid4(), name="Wheat")
    return FarmerCrop(
        id=uuid4(),
        farmer_id=user_id,
        farm_id=farm.id,
        crop_id=crop.id,
        crop=crop,
        growth_stage="vegetative",
        is_active=True,
    )


def _weather(
    farm: Farm,
    *,
    severe: bool = False,
    fetched_at=None,
    current_available: bool = True,
    forecast_rainfall: float | None = 2.0,
) -> NormalizedWeather:
    now = datetime.now(UTC)
    current = (
        HourlyWeather(now, 22.0, 60.0, 0.0, 5.0, "clear")
        if current_available
        else None
    )
    forecast = DailyWeather(
        now + timedelta(days=1), 18.0, 25.0, forecast_rainfall, 20.0, "clear"
    )
    events = (
        (
            SevereWeather(
                "Provider storm warning",
                "Provider event",
                "high",
                now + timedelta(hours=3),
            ),
        )
        if severe
        else ()
    )
    return NormalizedWeather(
        farm_id=farm.id,
        provider="test-provider",
        fetched_at=fetched_at or now,
        current=current,
        hourly=(current,) if current else (),
        daily=(forecast,),
        severe=events,
    )


def _client(monkeypatch, user_id, farms, crops, weather, engine=None):
    from app.api.v1.routes import recommendations as route

    session = RecommendationSession(user_id, farms, crops)

    class StubWeatherService:
        def __init__(self, *_args) -> None:
            pass

        def get_weather(self, farm, *, refresh=False):
            assert refresh is True
            if isinstance(weather, Exception):
                raise weather
            return weather[farm.id]

    monkeypatch.setattr(route, "WeatherService", StubWeatherService)
    monkeypatch.setattr(route, "build_provider", lambda _settings: object())
    monkeypatch.setattr(route, "build_cache", lambda _settings: None)
    if engine is not None:
        monkeypatch.setattr(route, "create_decision_engine", lambda: engine)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="unused",
        display_name="Farmer",
        is_active=True,
    )
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app), session


def test_recommendations_returns_rule_triggered_severe_weather_decision(monkeypatch) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    crop = _crop(user_id, farm)
    engine = AgriculturalDecisionEngine(AgriculturalThresholds())
    client, session = _client(
        monkeypatch,
        user_id,
        [farm],
        [crop],
        {farm.id: _weather(farm, severe=True)},
        engine,
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    extreme = next(
        item for item in body["farms"][0]["recommendations"]
        if item["recommendationType"] == "extreme_weather"
    )
    assert extreme["decision"] == "HIGH_RISK"
    assert extreme["riskLevel"] == "HIGH"
    assert extreme["cropName"] == "Wheat"
    assert extreme["reasons"] == ["The trusted forecast contains a severe-weather signal"]
    assert session.committed


def test_recommendations_without_owned_farm_returns_actionable_empty_state(monkeypatch) -> None:
    user_id = uuid4()
    client, _ = _client(monkeypatch, user_id, [], [], {})

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    assert response.json() == {
        "status": "insufficient_data",
        "message": "Add a farm with its location before requesting recommendations.",
        "farms": [],
    }


def test_recommendations_weather_failure_is_explicit_and_returns_no_decisions(monkeypatch) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    client, _ = _client(
        monkeypatch,
        user_id,
        [farm],
        [],
        WeatherProviderError("provider unavailable"),
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == (
        "Current farm weather is unavailable; recommendations were not generated."
    )


def test_recommendations_missing_soil_moisture_returns_rule_reason(monkeypatch) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    farm.soil_type = "loam"
    farm.irrigation_type = "drip"
    crop = _crop(user_id, farm)
    thresholds = AgriculturalThresholds.from_mapping(
        {
            "irrigation_profiles": [
                {
                    "crop": "Wheat",
                    "soil_type": "loam",
                    "irrigation_type": "drip",
                    "soil_moisture": {"sufficient_percent": 50},
                    "forecast": {"rainfall_lookahead_mm": 10, "horizon_days": 3},
                    "source": {
                        "publisher": "Test source",
                        "document_title": "Reviewed test rule",
                        "reviewed_by": "Agronomist",
                    },
                }
            ]
        }
    )
    client, _ = _client(
        monkeypatch,
        user_id,
        [farm],
        [crop],
        {farm.id: _weather(farm)},
        AgriculturalDecisionEngine(thresholds),
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    irrigation = next(
        item
        for item in response.json()["farms"][0]["recommendations"]
        if item["recommendationType"] == "irrigation"
    )
    assert irrigation["status"] == "needs_input"
    assert irrigation["reasons"] == [
        "Soil-moisture measurement is required for this irrigation profile"
    ]


def test_recommendations_are_authenticated_and_filter_farms_by_owner(monkeypatch) -> None:
    user_id = uuid4()
    other_user_id = uuid4()
    own_farm = _farm(user_id)
    foreign_farm = _farm(other_user_id)
    session = RecommendationSession(user_id, [own_farm, foreign_farm], [])
    from app.api.v1.routes import recommendations as route

    monkeypatch.setattr(
        route,
        "WeatherService",
        lambda *_args: type(
            "Stub", (), {"get_weather": lambda _self, farm, **_kw: _weather(farm)}
        )(),
    )
    monkeypatch.setattr(route, "build_provider", lambda _settings: object())
    monkeypatch.setattr(route, "build_cache", lambda _settings: None)
    monkeypatch.setattr(
        route,
        "create_decision_engine",
        lambda: AgriculturalDecisionEngine(AgriculturalThresholds()),
    )
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app) as client:
        unauthenticated = client.get("/api/v1/recommendations")
    assert unauthenticated.status_code == 401

    app.dependency_overrides[get_current_user] = lambda: User(
        id=user_id,
        email="farmer@example.com",
        password_hash="unused",
        display_name="Farmer",
        is_active=True,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    assert [item["farmId"] for item in response.json()["farms"]] == [str(own_farm.id)]
    assert any("farms.owner_id" in statement for statement in session.statements)


def test_recommendations_ignore_stale_weather(monkeypatch) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    stale = _weather(farm, severe=True, fetched_at=datetime.now(UTC) - timedelta(hours=2))
    client, _ = _client(
        monkeypatch,
        user_id,
        [farm],
        [],
        {farm.id: stale},
        AgriculturalDecisionEngine(AgriculturalThresholds()),
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    extreme = next(
        item
        for item in response.json()["farms"][0]["recommendations"]
        if item["recommendationType"] == "extreme_weather"
    )
    assert extreme["decision"] == "NEEDS_INPUT"


def test_recommendations_do_not_report_extreme_weather_low_risk_without_measurement(
    monkeypatch,
) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    thresholds = AgriculturalThresholds.from_mapping(
        {
            "extreme_temperature_high_celsius": 35,
            "source_notes": {"extreme_temperature_high_celsius": "Reviewed test rule"},
        }
    )
    client, _ = _client(
        monkeypatch,
        user_id,
        [farm],
        [],
        {farm.id: _weather(farm, current_available=False)},
        AgriculturalDecisionEngine(thresholds),
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    extreme = next(
        item
        for item in response.json()["farms"][0]["recommendations"]
        if item["recommendationType"] == "extreme_weather"
    )
    assert extreme["decision"] == "NEEDS_INPUT"
    assert extreme["status"] == "needs_input"
    assert extreme["reasons"] == [
        "Current temperature is required by the configured extreme-weather rule"
    ]


def test_recommendations_do_not_assume_zero_rain_for_spraying(monkeypatch) -> None:
    user_id = uuid4()
    farm = _farm(user_id)
    thresholds = AgriculturalThresholds.from_mapping(
        {
            "spray_rainfall_lookahead_mm": 5,
            "spray_min_humidity_percent": 20,
            "spray_max_humidity_percent": 90,
            "spray_max_wind_speed_kph": 10,
            "source_notes": {
                "spray_rainfall_lookahead_mm": "Reviewed test rule",
                "spray_min_humidity_percent": "Reviewed test rule",
                "spray_max_humidity_percent": "Reviewed test rule",
                "spray_max_wind_speed_kph": "Reviewed test rule",
            },
        }
    )
    client, _ = _client(
        monkeypatch,
        user_id,
        [farm],
        [],
        {farm.id: _weather(farm, forecast_rainfall=None)},
        AgriculturalDecisionEngine(thresholds),
    )

    response = client.get("/api/v1/recommendations")

    assert response.status_code == 200
    spraying = next(
        item
        for item in response.json()["farms"][0]["recommendations"]
        if item["recommendationType"] == "spraying"
    )
    assert spraying["decision"] == "NEEDS_INPUT"
    assert spraying["status"] == "needs_input"
    assert spraying["reasons"] == [
        "Forecast rainfall is required by the configured spraying rule"
    ]
