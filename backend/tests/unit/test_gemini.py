import httpx
import pytest

from app.conversation.gemini import GeminiChatService, GeminiConfigurationError, GeminiResponseError
from app.core.config import Settings


def test_gemini_response_uses_key_and_returns_generated_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert request.url.path.endswith("/models/gemini-3.6-flash:generateContent")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Use drip irrigation tomorrow."}]}}
                ]
            },
        )

    service = GeminiChatService(
        Settings(jwt_secret_key="x" * 32, gemini_api_key="test-key"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert service.respond("Should I irrigate?", "en", "No live weather is available.") == (
        "Use drip irrigation tomorrow."
    )


def test_gemini_response_requires_a_key() -> None:
    service = GeminiChatService(Settings(jwt_secret_key="x" * 32, gemini_api_key=None))

    with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY"):
        service.respond("Hello", "en", "No context")


def test_gemini_response_surfaces_provider_errors() -> None:
    service = GeminiChatService(
        Settings(jwt_secret_key="x" * 32, gemini_api_key="test-key"),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    404, json={"error": {"message": "models/gemini-unknown was not found"}}
                )
            )
        ),
    )

    with pytest.raises(GeminiResponseError, match="gemini-unknown"):
        service.respond("Hello", "en", "No context")
