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
    if any(term in normalized for term in ("warning", "alert", "वादळ", "चेतावणी")):
        return WeatherIntent.WEATHER_ALERT
    if any(
        term in normalized
        for term in ("forecast", "next three", "next 3", "tomorrow", "उद्या", "अंदाज")
    ):
        return WeatherIntent.FORECAST
    if any(term in normalized for term in ("rainfall", "raining", "पर्जन्यमान", "पाऊस", "बारिश")):
        return WeatherIntent.RAINFALL
    if any(term in normalized for term in ("weather", "temperature", "हवामान", "मौसम")):
        return WeatherIntent.CURRENT_WEATHER
    return WeatherIntent.UNKNOWN
