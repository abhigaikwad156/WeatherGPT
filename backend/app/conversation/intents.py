"""Intent detection for the first conversational API version."""

from enum import StrEnum


class WeatherIntent(StrEnum):
    CURRENT_WEATHER = "CURRENT_WEATHER"
    FORECAST = "FORECAST"
    RAINFALL = "RAINFALL"
    WEATHER_ALERT = "WEATHER_ALERT"
    UNKNOWN = "UNKNOWN"


def detect_intent(message: str) -> WeatherIntent:
    """Classify weather questions without attempting to answer them."""
    normalized = " ".join(message.casefold().split())
    if not normalized:
        return WeatherIntent.UNKNOWN
    if any(
        term in normalized
        for term in (
            "warning",
            "alert",
            "storm",
            "frost",
            "heatwave",
            "वादळ",
            "चेतावणी",
            "इशारा",
            "तूफान",
            "लू",
        )
    ):
        return WeatherIntent.WEATHER_ALERT
    if any(
        term in normalized
        for term in (
            "forecast",
            "next three",
            "next 3",
            "tomorrow",
            "this week",
            "next week",
            "उद्या",
            "पुढील",
            "अंदाज",
            "कल",
            "पूर्वानुमान",
            "अगले",
        )
    ):
        return WeatherIntent.FORECAST
    if any(
        term in normalized
        for term in (
            "rainfall",
            "raining",
            "precipitation",
            "rain",
            "पर्जन्यमान",
            "पाऊस",
            "पावस",
            "बारिश",
        )
    ):
        return WeatherIntent.RAINFALL
    if any(
        term in normalized
        for term in (
            "weather",
            "temperature",
            "current",
            "conditions",
            "how hot",
            "how cold",
            "हवामान",
            "तापमान",
            "गरमी",
            "थंडी",
            "मौसम",
            "गर्मी",
            "ठंड",
        )
    ):
        return WeatherIntent.CURRENT_WEATHER
    return WeatherIntent.UNKNOWN
