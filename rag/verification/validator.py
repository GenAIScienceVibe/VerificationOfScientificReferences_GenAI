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
import re

from pydantic import ValidationError

from rag.prompts.verifier import attach_human_review_flag
from rag.verification.models import Verdict, VerificationOutput

logger = logging.getLogger(__name__)

FALLBACK_EXPLANATION_PREFIX = "Automatic NEEDS_HUMAN_REVIEW fallback — LLM output failed validation"

# verify.j2 wraps the parseable JSON in [FINAL VERDICT JSON]...[/FINAL VERDICT
# JSON] tags, separating it from the preceding [THOUGHT PROCESS] free-form
# reasoning block so that reasoning text never has to be valid JSON itself.
_FINAL_VERDICT_JSON_PATTERN = re.compile(
    r"\[FINAL VERDICT JSON\](.*?)\[/FINAL VERDICT JSON\]", re.DOTALL
)


# ── Private helpers ───────────────────────────────────────────────────────────


def _extract_final_verdict_json(raw_text: str) -> str:
    """
    Pull out only the content between [FINAL VERDICT JSON] and
    [/FINAL VERDICT JSON] tags.

    If the tags aren't found (e.g. an older prompt format, or the LLM
    dropped them), returns raw_text unchanged so the existing
    json.JSONDecodeError handling in validate_output() catches the failure
    the same way it always has — this function never raises on its own.

    The LLM sometimes emits a stray character or extra whitespace right
    around the tag/JSON boundary (e.g. a leading backtick before the
    opening brace), which survives a plain .strip() since it isn't
    whitespace. After isolating the tagged section (or falling back to the
    whole text), this also trims down to the outermost {...} braces when
    both are present, discarding any such stray characters without
    touching well-formed JSON.
    """
    match = _FINAL_VERDICT_JSON_PATTERN.search(raw_text)
    candidate = match.group(1) if match is not None else raw_text
    candidate = candidate.strip()

    brace_start = candidate.find("{")
    brace_end = candidate.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        candidate = candidate[brace_start : brace_end + 1]

    return candidate


def _normalize_evidence_used(data: dict) -> dict:
    """
    Normalize evidence_used entries that are full dict objects (the LLM
    sometimes echoes back a chunk's metadata instead of just its id) down
    to the chunk_id string, since VerificationOutput expects
    evidence_used: list[str]. Entries that are already strings, or dicts
    without a "chunk_id" key, are passed through unchanged.
    """
    evidence_used = data.get("evidence_used")
    if not isinstance(evidence_used, list):
        return data

    data["evidence_used"] = [
        item["chunk_id"] if isinstance(item, dict) and "chunk_id" in item else item
        for item in evidence_used
    ]
    return data


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
        raw_json: Raw LLM response text returned by generate_verdict(). Since
            verify.j2, this contains a [THOUGHT PROCESS] block followed by a
            [FINAL VERDICT JSON] block — only the content inside the latter
            is parsed as JSON; the free-form reasoning before it is discarded
            here (it already informed the LLM's own answer, so nothing is
            lost by not parsing it as data).
        low_confidence: The low_confidence flag from VectorStoreOutput, if any —
            forwarded to attach_human_review_flag() per the SCRUM-196 rule.

    Returns:
        A validated VerificationOutput. On any failure (malformed JSON,
        missing "verdict"/"confidence", a schema mismatch such as an
        unrecognised verdict label or out-of-range confidence, or no content
        at all — e.g. the OpenAI SDK's response.choices[0].message.content
        can itself be None), returns the NEEDS_HUMAN_REVIEW fallback instead
        of raising.
    """
    if not isinstance(raw_json, str):
        logger.error("LLM verification response had no content (got %r)", raw_json)
        return _fallback_output(f"empty or non-string LLM response ({raw_json!r})")

    final_verdict_json = _extract_final_verdict_json(raw_json)

    try:
        data = attach_human_review_flag(final_verdict_json, low_confidence)
    except json.JSONDecodeError as exc:
        logger.error("LLM verification response is not valid JSON: %s", exc)
        return _fallback_output(f"malformed JSON ({exc})")
    except KeyError as exc:
        logger.error("LLM verification response is missing required field %s", exc)
        return _fallback_output(f"missing required field {exc}")

    data = _normalize_evidence_used(data)

    try:
        return VerificationOutput(**data)
    except ValidationError as exc:
        logger.error("LLM verification response does not match VerificationOutput schema: %s", exc)
        return _fallback_output(f"schema validation error ({exc})")
