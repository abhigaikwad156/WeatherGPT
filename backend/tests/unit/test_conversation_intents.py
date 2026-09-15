import pytest

from app.conversation.intents import WeatherIntent, detect_intent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the weather today?", WeatherIntent.CURRENT_WEATHER),
        ("Will it rain tomorrow?", WeatherIntent.FORECAST),
        ("How much rainfall did we get?", WeatherIntent.RAINFALL),
        ("Is there a weather warning near my farm?", WeatherIntent.WEATHER_ALERT),
        ("आज हवामान कसे आहे?", WeatherIntent.CURRENT_WEATHER),
        ("उद्या पाऊस पडेल का?", WeatherIntent.FORECAST),
        ("कल मौसम कैसा रहेगा?", WeatherIntent.FORECAST),
        ("Should I sell my wheat today?", WeatherIntent.UNKNOWN),
    ],
)
def test_detect_intent(question: str, expected: WeatherIntent) -> None:
    assert detect_intent(question) is expected
