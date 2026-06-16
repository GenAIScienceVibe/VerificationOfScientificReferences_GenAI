"""
Prompt template + LLM call module for LLM verification (SCRUM-193).

Responsibility: render the Jinja2 prompt template (templates/verify.j2)
with the claim, citation type, DOI, and retrieved evidence chunks, then
make one LLM call (Llama 4 Scout via OpenRouter) at temperature=0. Returns
the raw response text — Pydantic validation against VerificationOutput
happens downstream in rag/verification/validator.py (SCRUM-253).

Key design choices:
  - render_prompt() is a pure function, separate from the API call, so the
    prompt text can be unit-tested without mocking the LLM.
  - temperature=0 (LLM_TEMPERATURE from rag.prompts.config): verification
    verdicts must be reproducible — the same claim and evidence should
    always produce the same verdict.
  - Lazy client: built inside generate_verdict(), not at import time, so
    tests can import this module without a real API key present (mirrors
    embedder.py / classifier.py).
"""

import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

from rag.prompts.config import LLM_TEMPERATURE
from rag.verification.models import VerificationInput

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

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content
