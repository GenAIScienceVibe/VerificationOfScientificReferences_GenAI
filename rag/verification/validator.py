"""
Pydantic output validation for the LLM verification step (SCRUM-253).

Responsibility: take the raw JSON string returned by
rag.prompts.verifier.generate_verdict() and turn it into a validated
VerificationOutput. Any failure along the way — malformed JSON, a missing
required field, or a field that doesn't match the schema (e.g. an
unrecognised verdict label) — is logged and converted into a safe
NEEDS_HUMAN_REVIEW fallback rather than propagating an exception, since an
unverifiable LLM response must never silently break the pipeline.

Key design choice: reuses attach_human_review_flag() from
rag.prompts.verifier (SCRUM-196) to inject the human_review_required flag
before constructing VerificationOutput, instead of recomputing the same
confidence/verdict rule here.
"""

import json
import logging

from pydantic import ValidationError

from rag.prompts.verifier import attach_human_review_flag
from rag.verification.models import Verdict, VerificationOutput

logger = logging.getLogger(__name__)

FALLBACK_EXPLANATION_PREFIX = "Automatic NEEDS_HUMAN_REVIEW fallback — LLM output failed validation"


# ── Private helpers ───────────────────────────────────────────────────────────


def _fallback_output(reason: str) -> VerificationOutput:
    """Build the safe NEEDS_HUMAN_REVIEW output returned when validation fails."""
    return VerificationOutput(
        verdict=Verdict.NEEDS_HUMAN_REVIEW,
        confidence=0.0,
        explanation=f"{FALLBACK_EXPLANATION_PREFIX}: {reason}",
        evidence_used=[],
        limitations=None,
        human_review_required=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────


def validate_output(raw_json: str, low_confidence: bool = False) -> VerificationOutput:
    """
    Parse and validate the raw LLM response into a VerificationOutput.

    Args:
        raw_json: Raw JSON string returned by generate_verdict().
        low_confidence: The low_confidence flag from VectorStoreOutput, if any —
            forwarded to attach_human_review_flag() per the SCRUM-196 rule.

    Returns:
        A validated VerificationOutput. On any failure (malformed JSON,
        missing "verdict"/"confidence", or a schema mismatch such as an
        unrecognised verdict label or out-of-range confidence), returns the
        NEEDS_HUMAN_REVIEW fallback instead of raising.
    """
    try:
        data = attach_human_review_flag(raw_json, low_confidence)
    except json.JSONDecodeError as exc:
        logger.error("LLM verification response is not valid JSON: %s", exc)
        return _fallback_output(f"malformed JSON ({exc})")
    except KeyError as exc:
        logger.error("LLM verification response is missing required field %s", exc)
        return _fallback_output(f"missing required field {exc}")

    try:
        return VerificationOutput(**data)
    except ValidationError as exc:
        logger.error("LLM verification response does not match VerificationOutput schema: %s", exc)
        return _fallback_output(f"schema validation error ({exc})")
