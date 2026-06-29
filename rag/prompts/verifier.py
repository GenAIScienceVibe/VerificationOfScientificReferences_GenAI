"""
Prompt template + LLM call module for LLM verification (SCRUM-193, SCRUM-196).

Responsibility: render the Jinja2 prompt template (templates/verify.j2)
with the claim, citation type, DOI, and retrieved evidence chunks, then
make one LLM call (Llama 4 Scout via OpenRouter) at temperature=0. Returns
the raw response text — full Pydantic validation against VerificationOutput
(including graceful handling of malformed JSON / missing fields) happens
downstream in rag/verification/validator.py (SCRUM-253).

This module also computes the human_review_required flag (SCRUM-196): once
the raw response's verdict and confidence are known, attach_human_review_flag()
applies the safety rule from CLAUDE.md so the flag is set correctly before
the result reaches validator.py.

Key design choices:
  - render_prompt() is a pure function, separate from the API call, so the
    prompt text can be unit-tested without mocking the LLM.
  - temperature=0 (LLM_TEMPERATURE from rag.prompts.config): verification
    verdicts must be reproducible — the same claim and evidence should
    always produce the same verdict.
  - Lazy client: built inside generate_verdict(), not at import time, so
    tests can import this module without a real API key present (mirrors
    embedder.py / classifier.py).
  - attach_human_review_flag() assumes the JSON is already well-formed with
    "verdict" and "confidence" present — it is not responsible for graceful
    fallback on malformed JSON or missing fields; that is validator.py's job.
"""

import json
import logging
import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

from rag.prompts.config import LLM_TEMPERATURE
from rag.verification.models import Verdict, VerificationInput

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LLM_MODEL = "meta-llama/llama-4-scout"

TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "verify.j2"

SYSTEM_PROMPT = (
    "You are a precise, evidence-grounded citation verifier. Always respond "
    "with valid JSON only — no markdown fences, no commentary outside the "
    "JSON object."
)

# Below this confidence, the verdict is flagged for human review (CLAUDE.md).
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.5

# How many times to retry the LLM call when the response is empty or None.
# OpenRouter occasionally returns an empty completion on the first attempt;
# retrying 2 more times (3 total) is enough to recover without notable delay.
MAX_LLM_RETRIES = 3

# Jinja2 environment, built once at import time. The template directory is
# fixed and known ahead of time, so there is no need to defer this like the
# OpenAI client (which depends on env vars that may not be set at import).
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Private helpers ───────────────────────────────────────────────────────────


def _build_client() -> OpenAI:
    """
    Build and return an OpenAI-compatible client pointed at OpenRouter.

    Raises EnvironmentError if OPENROUTER_API_KEY is not set, with a clear
    message so developers know exactly what is missing.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )
    return OpenAI(api_key=api_key, base_url=base_url)


# ── Public API ────────────────────────────────────────────────────────────────


def render_prompt(input_data: VerificationInput) -> str:
    """
    Render the verify.j2 template with the given verification input.

    Args:
        input_data: claim text, citation type, evidence chunks, and DOI.

    Returns:
        The fully rendered prompt string, ready to send as the user message.
    """
    template = _jinja_env.get_template(TEMPLATE_NAME)
    return template.render(
        claim_text=input_data.claim_text,
        citation_type=input_data.citation_type,
        doi=input_data.doi,
        chunks=input_data.chunks,
    )


def generate_verdict(input_data: VerificationInput) -> str:
    """
    Render the verification prompt and call the LLM once.

    Args:
        input_data: claim text, citation type, evidence chunks, and DOI.

    Returns:
        The raw LLM response text (expected to be a JSON string matching
        VerificationOutput — validated separately by validator.py).

    Raises:
        EnvironmentError: if OPENROUTER_API_KEY is not set.
        openai.APIError:  on any non-retryable API error.
    """
    client = _build_client()
    prompt = render_prompt(input_data)

    logger.info(
        "DOI %s — calling %s for verification (citation_type=%s, %d evidence chunks).",
        input_data.doi, LLM_MODEL, input_data.citation_type, len(input_data.chunks),
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    last_content: str | None = None
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            messages=messages,
        )
        last_content = response.choices[0].message.content
        if not last_content or not last_content.strip():
            logger.warning(
                "DOI %s — empty LLM response on attempt %d/%d, retrying.",
                input_data.doi, attempt, MAX_LLM_RETRIES,
            )
            continue
        # Quick JSON recoverability check: strip control chars and trailing text,
        # then verify a JSON object can be decoded. Only accept the response if it
        # is recoverable; otherwise retry to get a cleaner completion.
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", last_content.strip())
        try:
            json.JSONDecoder().raw_decode(cleaned)
            return last_content
        except json.JSONDecodeError:
            logger.warning(
                "DOI %s — malformed JSON on attempt %d/%d, retrying.",
                input_data.doi, attempt, MAX_LLM_RETRIES,
            )

    # All retries exhausted; return whatever we have (validator.py handles malformed JSON).
    return last_content or ""


def compute_human_review_required(
    verdict: Verdict | str, confidence: float, low_confidence: bool = False
) -> bool:
    """
    Decide whether a verdict must be flagged for human review.

    Per CLAUDE.md, human_review_required is True when any of:
      - confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD (0.5)
      - verdict == PARTIALLY_SUPPORTED
      - low_confidence is True (flag carried over from the vector store's
        retrieval_confidence, set when the best retrieved chunk scored
        below the retrieval similarity threshold)

    Args:
        verdict: The LLM's verdict label (Verdict enum member or matching string).
        confidence: The LLM's confidence score (0.0–1.0).
        low_confidence: The low_confidence flag from VectorStoreOutput, if any.

    Returns:
        True if any trigger condition is met, False otherwise.
    """
    verdict_value = verdict.value if isinstance(verdict, Verdict) else verdict
    return (
        confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD
        or verdict_value == Verdict.PARTIALLY_SUPPORTED.value
        or low_confidence
    )


def attach_human_review_flag(raw_json: str, low_confidence: bool = False) -> dict:
    """
    Parse the raw LLM JSON response and inject the human_review_required flag.

    This is a thin step between generate_verdict() and validator.py: it
    assumes raw_json is well-formed and contains "verdict" and "confidence"
    keys. Malformed JSON or missing-field fallback handling belongs to
    validator.py (SCRUM-253), not here.

    Args:
        raw_json: Raw JSON string returned by generate_verdict().
        low_confidence: The low_confidence flag from VectorStoreOutput, if any.

    Returns:
        The parsed dict with "human_review_required" set per the rules in
        compute_human_review_required().

    Raises:
        json.JSONDecodeError: if raw_json is not valid JSON.
        KeyError: if "verdict" or "confidence" is missing.
    """
    data = json.loads(raw_json)
    data["human_review_required"] = compute_human_review_required(
        data["verdict"], data["confidence"], low_confidence
    )
    return data
