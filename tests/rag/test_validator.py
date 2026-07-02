"""
Unit tests for rag/verification/validator.py (SCRUM-253).

Covers: valid output parses correctly, malformed JSON falls back, missing
required fields fall back, schema mismatches fall back, and all failures
are logged.
"""

import json
import logging

import pytest

from rag.verification.models import Verdict, VerificationOutput
from rag.verification.validator import validate_output


# ── Valid output ─────────────────────────────────────────────────────────────


def test_validate_output_parses_valid_supported_response():
    raw_json = json.dumps(
        {
            "verdict": "SUPPORTED",
            "confidence": 0.95,
            "explanation": "The source confirms the claim exactly.",
            "evidence_used": ["chunk_001"],
            "limitations": None,
        }
    )

    result = validate_output(raw_json)

    assert isinstance(result, VerificationOutput)
    assert result.verdict == Verdict.SUPPORTED
    assert result.confidence == 0.95
    assert result.evidence_used == ["chunk_001"]
    assert result.human_review_required is False


def test_validate_output_sets_human_review_true_for_partially_supported():
    raw_json = json.dumps(
        {
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": 0.72,
            "explanation": "Partial match.",
            "evidence_used": ["chunk_001"],
            "limitations": "Abstract only.",
        }
    )

    result = validate_output(raw_json)

    assert result.verdict == Verdict.PARTIALLY_SUPPORTED
    assert result.human_review_required is True


def test_validate_output_sets_human_review_true_when_low_confidence_flag_passed():
    raw_json = json.dumps(
        {
            "verdict": "SUPPORTED",
            "confidence": 0.99,
            "explanation": "Strong match.",
        }
    )

    result = validate_output(raw_json, low_confidence=True)

    assert result.human_review_required is True


def test_validate_output_defaults_evidence_used_and_limitations_when_absent():
    raw_json = json.dumps(
        {
            "verdict": "NOT_SUPPORTED",
            "confidence": 0.9,
            "explanation": "Contradicts the source.",
        }
    )

    result = validate_output(raw_json)

    assert result.evidence_used == []
    assert result.limitations is None


# ── Malformed JSON ───────────────────────────────────────────────────────────


def test_validate_output_falls_back_on_malformed_json():
    result = validate_output("this is not json {{{")

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True
    assert result.confidence == 0.0
    assert "malformed JSON" in result.explanation


def test_validate_output_falls_back_on_empty_string():
    result = validate_output("")

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True


def test_validate_output_logs_error_on_malformed_json(caplog):
    with caplog.at_level(logging.ERROR, logger="rag.verification.validator"):
        validate_output("not json")

    assert any("not valid JSON" in record.message for record in caplog.records)


# ── Missing required fields ─────────────────────────────────────────────────


def test_validate_output_falls_back_when_verdict_missing():
    raw_json = json.dumps({"confidence": 0.8, "explanation": "x"})

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True
    assert "missing required field" in result.explanation


def test_validate_output_falls_back_when_confidence_missing():
    raw_json = json.dumps({"verdict": "SUPPORTED", "explanation": "x"})

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True


def test_validate_output_falls_back_when_explanation_missing():
    """explanation is required by VerificationOutput but not checked by attach_human_review_flag."""
    raw_json = json.dumps({"verdict": "SUPPORTED", "confidence": 0.9})

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True
    assert "schema validation error" in result.explanation


def test_validate_output_logs_error_on_missing_field(caplog):
    raw_json = json.dumps({"confidence": 0.8, "explanation": "x"})

    with caplog.at_level(logging.ERROR, logger="rag.verification.validator"):
        validate_output(raw_json)

    assert any("missing required field" in record.message for record in caplog.records)


# ── Schema mismatches ────────────────────────────────────────────────────────


def test_validate_output_falls_back_on_unrecognised_verdict_label():
    raw_json = json.dumps({"verdict": "MAYBE_SUPPORTED", "confidence": 0.5, "explanation": "x"})

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True
    assert "schema validation error" in result.explanation


def test_validate_output_falls_back_on_out_of_range_confidence():
    raw_json = json.dumps({"verdict": "SUPPORTED", "confidence": 1.5, "explanation": "x"})

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert result.human_review_required is True


def test_validate_output_logs_error_on_schema_mismatch(caplog):
    raw_json = json.dumps({"verdict": "MAYBE_SUPPORTED", "confidence": 0.5, "explanation": "x"})

    with caplog.at_level(logging.ERROR, logger="rag.verification.validator"):
        validate_output(raw_json)

    assert any("does not match VerificationOutput schema" in record.message for record in caplog.records)


# ── Verdict label normalisation ───────────────────────────────────────────────


def test_validate_output_normalises_verdict_label_with_space():
    """LLM returns "INSUFFICIENT EVIDENCE" (space) — should parse as INSUFFICIENT_EVIDENCE."""
    raw_json = json.dumps(
        {
            "verdict": "INSUFFICIENT EVIDENCE",
            "confidence": 0.0,
            "explanation": "Not enough information to verify.",
            "evidence_used": [],
            "limitations": None,
        }
    )

    result = validate_output(raw_json)

    assert result.verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert result.human_review_required is True


def test_validate_output_normalises_verdict_label_mixed_case():
    """LLM returns "not_supported" (lowercase) — should parse as NOT_SUPPORTED."""
    raw_json = json.dumps(
        {
            "verdict": "not_supported",
            "confidence": 0.88,
            "explanation": "The claim is contradicted by the source.",
            "evidence_used": ["chunk_001"],
            "limitations": None,
        }
    )

    result = validate_output(raw_json)

    assert result.verdict == Verdict.NOT_SUPPORTED
    assert result.confidence == 0.88
