"""
Unit tests for rag/prompts/verifier.py (SCRUM-193).

render_prompt() is tested directly (pure function, no mocking needed).
generate_verdict() mocks the OpenAI client so no real API calls are made.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from rag.ingestion.models import ChunkMetadata
from rag.prompts.verifier import (
    HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
    LLM_MODEL,
    attach_human_review_flag,
    compute_human_review_required,
    generate_verdict,
    render_prompt,
)
from rag.prompts.config import LLM_TEMPERATURE
from rag.verification.models import Verdict, VerificationInput


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
    assert "Read the claim" in prompt
    assert "Find the evidence" in prompt
    assert "Compare" in prompt
    assert "Select the verdict" in prompt


def test_render_prompt_requires_thought_process_and_final_verdict_blocks():
    """verify.j2 isolates free-form reasoning from the strict JSON output
    using [THOUGHT PROCESS]/[FINAL VERDICT JSON] tags, so validator.py can
    extract only the JSON block before parsing (see
    rag.verification.validator._extract_final_verdict_json)."""
    prompt = render_prompt(make_input())
    assert '"explanation"' in prompt
    assert "[THOUGHT PROCESS]" in prompt
    assert "[/THOUGHT PROCESS]" in prompt
    assert "[FINAL VERDICT JSON]" in prompt
    assert "[/FINAL VERDICT JSON]" in prompt


# ── generate_verdict — success path ─────────────────────────────────────────


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_returns_raw_llm_content(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response(FAKE_JSON_VERDICT)
    mock_openai_cls.return_value = mock_client

    result = generate_verdict(make_input())

    assert result == FAKE_JSON_VERDICT


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
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


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
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


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
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
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(EnvironmentError):
        generate_verdict(make_input())


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
@patch("rag.prompts.verifier.OpenAI")
def test_generate_verdict_propagates_api_errors(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("connection reset")
    mock_openai_cls.return_value = mock_client

    with pytest.raises(RuntimeError):
        generate_verdict(make_input())


# ── compute_human_review_required (SCRUM-196) ───────────────────────────────


def test_human_review_not_required_when_no_trigger_present():
    assert compute_human_review_required(Verdict.SUPPORTED, 0.9, low_confidence=False) is False


def test_human_review_required_when_confidence_below_threshold():
    assert compute_human_review_required(Verdict.SUPPORTED, 0.49, low_confidence=False) is True


def test_human_review_not_required_at_exact_threshold():
    """confidence == threshold should NOT trigger — only strictly below."""
    assert (
        compute_human_review_required(
            Verdict.SUPPORTED, HUMAN_REVIEW_CONFIDENCE_THRESHOLD, low_confidence=False
        )
        is False
    )


def test_human_review_required_when_verdict_is_partially_supported():
    assert compute_human_review_required(Verdict.PARTIALLY_SUPPORTED, 0.95, low_confidence=False) is True


def test_human_review_required_when_verdict_is_partially_supported_as_string():
    assert compute_human_review_required("PARTIALLY_SUPPORTED", 0.95, low_confidence=False) is True


def test_human_review_required_when_low_confidence_flag_set():
    assert compute_human_review_required(Verdict.SUPPORTED, 0.95, low_confidence=True) is True


def test_human_review_required_when_multiple_triggers_present():
    assert compute_human_review_required(Verdict.PARTIALLY_SUPPORTED, 0.2, low_confidence=True) is True


@pytest.mark.parametrize(
    "verdict",
    [
        Verdict.SUPPORTED,
        Verdict.NOT_SUPPORTED,
        Verdict.INSUFFICIENT_EVIDENCE,
        Verdict.NEEDS_HUMAN_REVIEW,
    ],
)
def test_human_review_not_required_for_other_verdicts_with_high_confidence(verdict):
    assert compute_human_review_required(verdict, 0.9, low_confidence=False) is False


# ── attach_human_review_flag (SCRUM-196) ────────────────────────────────────


def test_attach_human_review_flag_sets_true_for_low_confidence_response():
    raw_json = json.dumps({"verdict": "SUPPORTED", "confidence": 0.3, "explanation": "x"})

    result = attach_human_review_flag(raw_json)

    assert result["human_review_required"] is True
    assert result["verdict"] == "SUPPORTED"
    assert result["confidence"] == 0.3


def test_attach_human_review_flag_sets_false_when_no_trigger():
    raw_json = json.dumps({"verdict": "SUPPORTED", "confidence": 0.95, "explanation": "x"})

    result = attach_human_review_flag(raw_json)

    assert result["human_review_required"] is False


def test_attach_human_review_flag_sets_true_for_partially_supported():
    raw_json = json.dumps({"verdict": "PARTIALLY_SUPPORTED", "confidence": 0.95, "explanation": "x"})

    result = attach_human_review_flag(raw_json)

    assert result["human_review_required"] is True


def test_attach_human_review_flag_sets_true_when_vector_store_low_confidence():
    raw_json = json.dumps({"verdict": "SUPPORTED", "confidence": 0.95, "explanation": "x"})

    result = attach_human_review_flag(raw_json, low_confidence=True)

    assert result["human_review_required"] is True


def test_attach_human_review_flag_raises_on_malformed_json():
    with pytest.raises(json.JSONDecodeError):
        attach_human_review_flag("not valid json")


def test_attach_human_review_flag_raises_on_missing_confidence():
    raw_json = json.dumps({"verdict": "SUPPORTED", "explanation": "x"})

    with pytest.raises(KeyError):
        attach_human_review_flag(raw_json)
