from uuid import uuid4

from app.conversation.explanation import WeatherExplanationService
from app.conversation.weather_tool import WeatherResult


def test_explanation_uses_verified_tool_result() -> None:
    result = WeatherResult(
        intent="CURRENT_WEATHER",
        farm_id=uuid4(),
        farm_name="Green Valley Farm",
        current={"temperature_celsius": 27},
        source="weather-provider",
    )

    response = WeatherExplanationService().explain(result, "en")

    assert "27" in response
    assert "Green Valley Farm" in response


def test_explanation_does_not_invent_unknown_weather_data() -> None:
    response = WeatherExplanationService().explain(None, "en")

    assert "verified weather data" in response
