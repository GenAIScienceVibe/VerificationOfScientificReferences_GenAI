"""
Citation type classifier for the verifAi RAG pipeline (SCRUM-252).

Responsibility: take a clean claim (author names already stripped) and make
one LLM call via OpenRouter to classify what kind of citation it is. This
classification is later injected into the verification prompt (verifier.py)
so the LLM judges the claim with the right context — e.g. a RESULT_COMPARISON
claim should be checked against numbers, while a BACKGROUND claim just needs
general topical support.

Key design choices:
  - Single call, no retries: unlike embeddings (a pipeline-critical step),
    classification only adds context to the verification prompt. If the call
    fails for any reason, we fall back to BACKGROUND (the safest, most
    general category) rather than blocking the pipeline.
  - temperature=0 (LLM_TEMPERATURE from rag.prompts.config): classification
    must be deterministic, otherwise the same claim could get a different
    citation type on every run.
  - Lazy client: built inside classify_citation_type(), not at import time,
    so tests can import this module without a real API key present.
"""

import logging
import os
from enum import Enum

from openai import OpenAI

from rag.prompts.config import LLM_TEMPERATURE

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LLM_MODEL = "meta-llama/llama-4-scout"

# Safest, most general fallback when classification fails or returns
# something we don't recognise.
DEFAULT_CITATION_TYPE_VALUE = "BACKGROUND"

SYSTEM_PROMPT = (
    "You are a citation type classifier for a scientific claim verification "
    "system. Read the claim and respond with EXACTLY ONE of the following "
    "labels, and nothing else:\n"
    "RESULT_COMPARISON, METHOD, BACKGROUND, MOTIVATION, EXTENSION, FUTURE_WORK\n\n"
    "RESULT_COMPARISON: the claim compares or reports a specific numeric/"
    "experimental result from the source.\n"
    "METHOD: the claim describes a technique, algorithm, or procedure from "
    "the source.\n"
    "BACKGROUND: the claim cites the source for general context or prior "
    "knowledge.\n"
    "MOTIVATION: the claim cites the source to justify why the current work "
    "matters.\n"
    "EXTENSION: the claim says the current work builds on or extends the "
    "source.\n"
    "FUTURE_WORK: the claim cites the source as a direction for future "
    "research."
)


class CitationType(str, Enum):
    """The six citation type labels the classifier can return."""

    RESULT_COMPARISON = "RESULT_COMPARISON"
    METHOD = "METHOD"
    BACKGROUND = "BACKGROUND"
    MOTIVATION = "MOTIVATION"
    EXTENSION = "EXTENSION"
    FUTURE_WORK = "FUTURE_WORK"


DEFAULT_CITATION_TYPE = CitationType(DEFAULT_CITATION_TYPE_VALUE)


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


def _parse_label(raw_content: str) -> CitationType:
    """
    Parse the LLM's raw text response into a CitationType.

    Raises ValueError if the cleaned response does not match any known label,
    so the caller can fall back to DEFAULT_CITATION_TYPE.
    """
    cleaned = raw_content.strip().upper()
    return CitationType(cleaned)


# ── Public API ────────────────────────────────────────────────────────────────


def classify_citation_type(claim_text: str) -> CitationType:
    """
    Classify a clean claim into one of the six citation types.

    Makes exactly one LLM call via OpenRouter at temperature=0. On any
    failure (missing API key, network/API error, or an unparseable response),
    logs a warning and falls back to CitationType.BACKGROUND so the pipeline
    is never blocked by a classification failure.

    Args:
        claim_text: Clean factual claim text (author names already stripped).

    Returns:
        The classified CitationType, or DEFAULT_CITATION_TYPE on failure.
    """
    try:
        client = _build_client()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": claim_text},
            ],
        )
        raw_content = response.choices[0].message.content
        return _parse_label(raw_content)

    except Exception as exc:
        logger.warning(
            "Citation type classification failed (%s) — falling back to %s.",
            exc, DEFAULT_CITATION_TYPE.value,
        )
        return DEFAULT_CITATION_TYPE
