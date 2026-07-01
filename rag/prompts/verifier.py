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
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

from rag.prompts.config import GROQ_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from rag.verification.models import Verdict, VerificationInput

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "verify.j2"

# Some OpenRouter-backing providers (observed: DeepInfra) intermittently
# return finish_reason="stop" with completion tokens billed but
# message.content=None. Retrying tends to land on a different provider
# (observed: Groq) that returns content normally for the same prompt.
NULL_CONTENT_MAX_ATTEMPTS = 3
NULL_CONTENT_RETRY_DELAY_SECONDS = 1

SYSTEM_PROMPT = (
    "You are a precise, evidence-grounded citation verifier. Always respond "
    "with valid JSON only — no markdown fences, no commentary outside the "
    "JSON object."
)

# Below this confidence, the verdict is flagged for human review (CLAUDE.md).
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.5

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
    Build and return an OpenAI-compatible client pointed at Groq.

    The LLM call goes directly to Groq (not OpenRouter) because DeepInfra,
    one of OpenRouter's backends for llama-4-scout, silently drops
    message.content on large prompts. Groq never exhibited this behaviour
    across 4 manual tests. The embedding call still uses OpenRouter.

    Raises EnvironmentError if GROQ_API_KEY is not set, with a clear
    message so developers know exactly what is missing.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY is not set. Add it to your .env file."
        )
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


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
        is_abstract_only=input_data.is_abstract_only,
        preceding_context=input_data.preceding_context,
    )


def generate_verdict(input_data: VerificationInput) -> str:
    """
    Render the verification prompt and call the LLM, retrying on null content.

    Args:
        input_data: claim text, citation type, evidence chunks, and DOI.

    Returns:
        The raw LLM response text (expected to be a JSON string matching
        VerificationOutput — validated separately by validator.py). May be
        None if every attempt returned null content; validator.py's
        None-guard handles that case.

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

    content = None
    for attempt in range(1, NULL_CONTENT_MAX_ATTEMPTS + 1):
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if content is not None:
            break

        if attempt < NULL_CONTENT_MAX_ATTEMPTS:
            logger.warning(
                "DOI %s — LLM call %d/%d returned null content; retrying in %ds.",
                input_data.doi, attempt, NULL_CONTENT_MAX_ATTEMPTS, NULL_CONTENT_RETRY_DELAY_SECONDS,
            )
            time.sleep(NULL_CONTENT_RETRY_DELAY_SECONDS)
        else:
            logger.error(
                "DOI %s — LLM call returned null content on all %d attempts.",
                input_data.doi, NULL_CONTENT_MAX_ATTEMPTS,
            )

    return content


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
