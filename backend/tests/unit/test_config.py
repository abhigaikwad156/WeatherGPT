import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_rejects_cors_wildcard() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(cors_origins=["*"])


def test_settings_uses_explicit_local_cors_origin() -> None:
    assert Settings().cors_origins == ["http://localhost:5173", "http://localhost:5174"]
