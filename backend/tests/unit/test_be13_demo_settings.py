from __future__ import annotations

from app.core.config import Settings


def test_be13_demo_and_mock_settings_are_available() -> None:
    settings = Settings(DEMO_MODE="true", METADATA_MOCK_MODE="true", GENAI_MOCK_MODE="true")
    assert settings.demo_mode is True
    assert settings.metadata_mock_mode is True
    assert settings.genai_mock_mode is True
    assert settings.groq_model == "meta-llama/llama-4-scout-17b-16e-instruct"
