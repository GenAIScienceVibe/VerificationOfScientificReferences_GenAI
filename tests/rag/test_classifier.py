"""
Unit tests for rag/prompts/classifier.py (SCRUM-252).

All tests mock the OpenAI client so no real API calls are made.

Mocking strategy:
  - We patch 'rag.prompts.classifier.OpenAI' so _build_client() returns a
    mock object. We then configure mock_client.chat.completions.create
    .return_value to look like a real chat-completion response.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from rag.prompts.classifier import (
    DEFAULT_CITATION_TYPE,
    LLM_MODEL,
    CitationType,
    _parse_label,
    classify_citation_type,
)
from rag.prompts.config import LLM_TEMPERATURE


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def fake_response(label: str) -> MagicMock:
    """Build a mock chat-completion response with the given label as content."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=label))]
    return response


# ── _parse_label ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("RESULT_COMPARISON", CitationType.RESULT_COMPARISON),
        ("method", CitationType.METHOD),
        ("  Background  ", CitationType.BACKGROUND),
        ("MOTIVATION\n", CitationType.MOTIVATION),
        ("extension", CitationType.EXTENSION),
        ("FUTURE_WORK", CitationType.FUTURE_WORK),
    ],
)
def test_parse_label_accepts_known_labels_case_and_whitespace_insensitive(raw, expected):
    assert _parse_label(raw) == expected


def test_parse_label_rejects_unknown_label():
    with pytest.raises(ValueError):
        _parse_label("NOT_A_REAL_LABEL")


def test_parse_label_rejects_empty_string():
    with pytest.raises(ValueError):
        _parse_label("")


# ── classify_citation_type — success path ───────────────────────────────────


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_returns_label_from_llm(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response("METHOD")
    mock_openai_cls.return_value = mock_client

    result = classify_citation_type("The algorithm follows the approach of Smith et al.")

    assert result == CitationType.METHOD


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_calls_chat_completions_with_temperature_zero(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response("BACKGROUND")
    mock_openai_cls.return_value = mock_client

    classify_citation_type("Some claim.")

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["temperature"] == LLM_TEMPERATURE
    assert kwargs["temperature"] == 0
    assert kwargs["model"] == LLM_MODEL


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_sends_claim_text_as_user_message(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response("MOTIVATION")
    mock_openai_cls.return_value = mock_client

    classify_citation_type("Exercise reduces heart disease risk.")

    _, kwargs = mock_client.chat.completions.create.call_args
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Exercise reduces heart disease risk."}


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_strips_and_uppercases_messy_llm_response(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response("  future_work \n")
    mock_openai_cls.return_value = mock_client

    result = classify_citation_type("Future studies should explore X.")

    assert result == CitationType.FUTURE_WORK


# ── classify_citation_type — fallback paths ─────────────────────────────────


def test_classify_falls_back_to_background_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = classify_citation_type("Some claim.")

    assert result == DEFAULT_CITATION_TYPE
    assert result == CitationType.BACKGROUND


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_falls_back_to_background_on_unparseable_response(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response("I'm not sure!")
    mock_openai_cls.return_value = mock_client

    result = classify_citation_type("Some claim.")

    assert result == DEFAULT_CITATION_TYPE


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_falls_back_to_background_on_api_exception(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("connection reset")
    mock_openai_cls.return_value = mock_client

    result = classify_citation_type("Some claim.")

    assert result == DEFAULT_CITATION_TYPE


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.classifier.OpenAI")
def test_classify_falls_back_when_response_has_no_choices(mock_openai_cls):
    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.choices = []
    mock_client.chat.completions.create.return_value = bad_response
    mock_openai_cls.return_value = mock_client

    result = classify_citation_type("Some claim.")

    assert result == DEFAULT_CITATION_TYPE


# ── CitationType enum ────────────────────────────────────────────────────────


def test_citation_type_has_exactly_six_labels():
    assert {c.value for c in CitationType} == {
        "RESULT_COMPARISON",
        "METHOD",
        "BACKGROUND",
        "MOTIVATION",
        "EXTENSION",
        "FUTURE_WORK",
    }


def test_default_citation_type_is_background():
    assert DEFAULT_CITATION_TYPE == CitationType.BACKGROUND
