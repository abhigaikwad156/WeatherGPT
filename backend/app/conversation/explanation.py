"""Explanation boundary for verified weather tool results."""

from app.conversation.weather_tool import WeatherResult


class WeatherExplanationService:
    """Create a user-facing explanation from tool output only.

    A future LLM adapter can implement this boundary, but it must receive the
    structured WeatherResult and must not answer without a tool result.
    """

    def explain(self, result: WeatherResult | None, language: str) -> str:
        if result is None:
            return "I could not find a farm or verified weather data for your account yet."
        if result.intent == "CURRENT_WEATHER":
            if not result.current:
                return f"I do not have current weather data for {result.farm_name} yet."
            temperature = result.current["temperature_celsius"]
            return f"The latest verified reading for {result.farm_name} is {temperature}°C."
        if result.intent == "FORECAST":
            count = len(result.forecast or [])
            return (
                f"I found a verified forecast for {count} upcoming day(s) near {result.farm_name}."
            )
        if result.intent == "RAINFALL":
            if result.rainfall_mm is None:
                return f"I do not have a verified rainfall reading for {result.farm_name} yet."
            return (
                f"The latest verified rainfall reading for {result.farm_name} is "
                f"{result.rainfall_mm} mm."
            )
        if result.intent == "WEATHER_ALERT":
            count = len(result.alerts or [])
            return (
                f"There {'is' if count == 1 else 'are'} {count} active weather "
                f"warning(s) near {result.farm_name}."
            )
        return "I can help with current weather, forecasts, rainfall, and weather warnings."
