"""Gemini-backed natural-language responses for the conversational API."""

from collections.abc import Mapping

import httpx

from app.core.config import Settings


class GeminiError(RuntimeError):
    """Base error for a Gemini request that could not produce a reply."""


class GeminiConfigurationError(GeminiError):
    """Raised when the application has no Gemini credential."""


class GeminiResponseError(GeminiError):
    """Raised when Gemini rejects a request or returns no usable text."""


class GeminiChatService:
    """Use Gemini when configured, without allowing it to fabricate live weather data."""

    _endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    _initial_max_output_tokens = 2_048
    _retry_max_output_tokens = 4_096

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self.client = client or httpx.Client(timeout=20)

    def respond(self, question: str, language: str, verified_context: str) -> str:
        if not self.api_key:
            raise GeminiConfigurationError(
                "Gemini is not configured. Set GEMINI_API_KEY and restart the backend."
            )
        payload = self._request_payload(
            question, language, verified_context, self._initial_max_output_tokens
        )
        try:
            response_payload = self._generate(payload)
            if self._finish_reason(response_payload) == "MAX_TOKENS":
                response_payload = self._generate(
                    self._request_payload(
                        question, language, verified_context, self._retry_max_output_tokens
                    )
                )
        except httpx.HTTPStatusError as error:
            raise GeminiResponseError(self._http_error_message(error)) from error
        except httpx.TimeoutException as error:
            raise GeminiResponseError(
                "Gemini did not respond before the request timed out."
            ) from error
        except httpx.HTTPError as error:
            raise GeminiResponseError("Could not connect to Gemini.") from error
        except (KeyError, TypeError, ValueError) as error:
            raise GeminiResponseError("Gemini returned an invalid response.") from error
        if self._finish_reason(response_payload) == "MAX_TOKENS":
            raise GeminiResponseError(
                "Gemini could not complete the answer within the response limit. Please try again."
            )
        text = self._response_text(response_payload)
        if text is None:
            raise GeminiResponseError("Gemini returned no text for this question.")
        return text

    def _request_payload(
        self, question: str, language: str, verified_context: str, max_output_tokens: int
    ) -> dict[str, object]:
        return {
            "system_instruction": {
                "parts": [
                    {
                        "text": (
                            "You are WeatherGPT, a practical agricultural assistant. "
                            "Reply in the user's requested language when possible. "
                            "You may give general farming guidance, but never invent live weather, "
                            "farm records, forecasts, or measurements. Treat the verified context "
                            "as the only source of live farm and weather facts. "
                            "For agricultural answers, preserve the supplied decision and reasons; "
                            "do not reverse or soften them. Refer to supplied crop, "
                            "farm conditions, and weather "
                            "measurements when available."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"Requested language: {language}\n"
                                f"Question: {question}\n\n"
                                f"Verified context: {verified_context}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }

    def _generate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        response = self.client.post(
            self._endpoint.format(model=self.model),
            headers={"x-goog-api-key": self.api_key},
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, Mapping):
            raise ValueError("Gemini response must be an object")
        return result

    @staticmethod
    def _http_error_message(error: httpx.HTTPStatusError) -> str:
        """Return Gemini's useful error text without exposing request credentials."""
        status_code = error.response.status_code
        try:
            payload = error.response.json()
            message = payload.get("error", {}).get("message")
        except (ValueError, AttributeError):
            message = None
        if isinstance(message, str) and message.strip():
            return f"Gemini request failed ({status_code}): {message.strip()}"
        return f"Gemini request failed ({status_code})."

    @staticmethod
    def _response_text(payload: Mapping[str, object]) -> str | None:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return None
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            return None
        content = candidate.get("content")
        if not isinstance(content, Mapping):
            return None
        parts = content.get("parts")
        if not isinstance(parts, list):
            return None
        text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        ).strip()
        return text or None

    @staticmethod
    def _finish_reason(payload: Mapping[str, object]) -> str | None:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return None
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            return None
        finish_reason = candidate.get("finishReason")
        return finish_reason if isinstance(finish_reason, str) else None
