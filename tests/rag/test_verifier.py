"""
Unit tests for rag/prompts/verifier.py (SCRUM-193).

render_prompt() is tested directly (pure function, no mocking needed).
generate_verdict() mocks the OpenAI client so no real API calls are made.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from rag.ingestion.models import ChunkMetadata
from rag.prompts.verifier import LLM_MODEL, generate_verdict, render_prompt
from rag.prompts.config import LLM_TEMPERATURE
from rag.verification.models import VerificationInput


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def make_chunk(index: int = 0, section: str = "results", text: str = "participants showed a 28% reduction...") -> ChunkMetadata:
    """Build a minimal ChunkMetadata for testing."""
    return ChunkMetadata(
        chunk_id=f"10_1234_example_2019_chunk_{index:03d}",
        section=section,
        priority=1.3,
        chunk_index=index,
        paper_doi="10.1234/example.2019.001",
        evidence_type="FULL_TEXT",
        chunk_text=text,
        token_count=6,
    )


def make_input(n_chunks: int = 1) -> VerificationInput:
    """Build a VerificationInput with n_chunks evidence chunks."""
    return VerificationInput(
        claim_text="Exercise reduces heart disease risk by 35%",
        citation_type="RESULT_COMPARISON",
        chunks=[make_chunk(i) for i in range(n_chunks)],
        doi="10.1234/example.2019.001",
    )


def fake_response(content: str) -> MagicMock:
    """Build a mock chat-completion response with the given content."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


FAKE_JSON_VERDICT = (
    '{"verdict": "PARTIALLY_SUPPORTED", "confidence": 0.72, '
    '"explanation": "The source reports 28% reduction, not 35% as claimed.", '
    '"evidence_used": ["10_1234_example_2019_chunk_000"], '
    '"limitations": "Only abstract-level evidence was available."}'
)


# ── render_prompt ────────────────────────────────────────────────────────────


def test_render_prompt_includes_claim_text():
    prompt = render_prompt(make_input())
    assert "Exercise reduces heart disease risk by 35%" in prompt


def test_render_prompt_includes_citation_type():
    prompt = render_prompt(make_input())
    assert "RESULT_COMPARISON" in prompt


def test_render_prompt_includes_doi():
    prompt = render_prompt(make_input())
    assert "10.1234/example.2019.001" in prompt


def test_render_prompt_includes_chunk_id_section_and_text():
    prompt = render_prompt(make_input(n_chunks=1))
    assert "10_1234_example_2019_chunk_000" in prompt
    assert "results" in prompt
    assert "participants showed a 28% reduction..." in prompt


def test_render_prompt_includes_all_chunks_when_multiple():
    prompt = render_prompt(make_input(n_chunks=3))
    for i in range(3):
        assert f"10_1234_example_2019_chunk_{i:03d}" in prompt


def test_render_prompt_handles_empty_chunks_list():
    prompt = render_prompt(make_input(n_chunks=0))
    assert "No evidence chunks were retrieved" in prompt


def test_render_prompt_instructs_json_only_output():
    prompt = render_prompt(make_input())
    assert "JSON" in prompt
    assert '"verdict"' in prompt
    assert '"confidence"' in prompt
    assert '"explanation"' in prompt
    assert '"evidence_used"' in prompt
    assert '"limitations"' in prompt


def test_render_prompt_lists_all_five_verdict_labels():
    prompt = render_prompt(make_input())
    for label in [
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "NEEDS_HUMAN_REVIEW",
    ]:
        assert label in prompt


# ── Chain-of-thought instructions (SCRUM-195) ───────────────────────────────


def test_render_prompt_instructs_step_by_step_reasoning():
    prompt = render_prompt(make_input())
    assert "step by step" in prompt


def test_render_prompt_requires_four_part_reasoning_structure():
    prompt = render_prompt(make_input())
    assert "What the claim says" in prompt
    assert "What the source evidence says" in prompt
    assert "Comparison" in prompt
    assert "Verdict reasoning" in prompt


def test_render_prompt_requires_reasoning_inside_explanation_field():
    prompt = render_prompt(make_input())
    assert '"explanation"' in prompt
    assert "four-step reasoning" in prompt


# ── generate_verdict — success path ─────────────────────────────────────────


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_returns_raw_llm_content(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response(FAKE_JSON_VERDICT)
    mock_openai_cls.return_value = mock_client

    result = generate_verdict(make_input())

    assert result == FAKE_JSON_VERDICT


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_preserves_four_step_reasoning_in_explanation(mock_openai_cls):
    """generate_verdict must not strip or alter the LLM's chain-of-thought reasoning."""
    cot_response = (
        '{"verdict": "PARTIALLY_SUPPORTED", "confidence": 0.72, '
        '"explanation": "1. What the claim says: exercise reduces risk by 35%. '
        '2. What the source evidence says: a 28% reduction was observed. '
        '3. Comparison: the source reports a smaller effect than claimed. '
        '4. Verdict reasoning: partial match, so PARTIALLY_SUPPORTED.", '
        '"evidence_used": ["10_1234_example_2019_chunk_000"], "limitations": null}'
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response(cot_response)
    mock_openai_cls.return_value = mock_client

    result = generate_verdict(make_input())

    assert "What the claim says" in result
    assert "What the source evidence says" in result
    assert "Comparison" in result
    assert "Verdict reasoning" in result


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_calls_correct_model_and_temperature(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response(FAKE_JSON_VERDICT)
    mock_openai_cls.return_value = mock_client

    generate_verdict(make_input())

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["model"] == LLM_MODEL
    assert kwargs["temperature"] == LLM_TEMPERATURE
    assert kwargs["temperature"] == 0


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_sends_system_and_user_messages(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response(FAKE_JSON_VERDICT)
    mock_openai_cls.return_value = mock_client

    input_data = make_input()
    generate_verdict(input_data)

    _, kwargs = mock_client.chat.completions.create.call_args
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert input_data.claim_text in messages[1]["content"]


# ── generate_verdict — failure path ─────────────────────────────────────────


def test_generate_verdict_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(EnvironmentError):
        generate_verdict(make_input())


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_propagates_api_errors(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("connection reset")
    mock_openai_cls.return_value = mock_client

    with pytest.raises(RuntimeError):
        generate_verdict(make_input())
