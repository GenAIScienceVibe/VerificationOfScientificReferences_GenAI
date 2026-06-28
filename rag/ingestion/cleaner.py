"""
Text cleaning module for the verifAi RAG pipeline (SCRUM-178).

Responsibility: receive raw plain text from the backend (already extracted
from a PDF) and return clean text ready for the section-aware chunker.

What we clean:
  1. Normalize whitespace (tabs, CRLF, multiple spaces)
  2. Remove page number lines
  3. Remove repeated short lines (running headers / footers)
  4. Remove the references / bibliography section from the end
  5. Collapse excessive blank lines

We do NOT parse PDFs — the backend sends us plain text.
"""

import logging
import re
from collections import Counter

from rag.ingestion.models import CleanerInput, CleanerOutput

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# A line appearing this many times or more is treated as a running header/footer.
REPEATED_LINE_THRESHOLD = 3

# Headings that mark the start of the references section (case-insensitive).
REFERENCE_SECTION_HEADINGS = re.compile(
    r"^\s*(?:\d+[\.\s]+)?"          # optional leading number like "9." or "9 "
    r"(references?|bibliography|works\s+cited)"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Common page-number line patterns produced by PDF-to-text converters.
PAGE_NUMBER_PATTERN = re.compile(
    r"^\s*"
    r"(?:"
    r"page\s+\d+\s*(?:of\s+\d+)?"   # "Page 3" or "Page 3 of 12"
    r"|\d+\s+of\s+\d+"               # "3 of 12"
    r"|[-–—]\s*\d+\s*[-–—]"          # "- 3 -"
    r"|\d+"                           # bare number on its own line
    r")"
    r"\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ── Private helpers ───────────────────────────────────────────────────────────


def _normalize_whitespace(text: str) -> str:
    """Replace tabs and CRLF with standard characters; collapse multi-spaces."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    # Collapse runs of spaces within a line (not newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text


def _remove_page_numbers(text: str) -> str:
    """Strip lines that contain only a page number or page-number pattern."""
    return PAGE_NUMBER_PATTERN.sub("", text)


def _remove_repeated_lines(text: str, threshold: int = REPEATED_LINE_THRESHOLD) -> str:
    """
    Remove lines that appear `threshold` or more times in the document.

    PDF-to-text conversion often duplicates running headers and footers
    (journal name, paper title, author list) on every page. Counting line
    frequency and stripping the most-repeated short ones removes this noise
    without touching real content.
    """
    lines = text.split("\n")

    # Only count short lines as candidate headers/footers (long lines are content)
    short_lines = [ln.strip() for ln in lines if 0 < len(ln.strip()) < 120]
    frequency = Counter(short_lines)

    # Build set of lines to remove (non-empty lines above the threshold)
    repeated = {line for line, count in frequency.items() if count >= threshold and line}

    if repeated:
        logger.debug("Removing %d repeated header/footer patterns", len(repeated))

    cleaned_lines = [ln for ln in lines if ln.strip() not in repeated]
    return "\n".join(cleaned_lines)


def _remove_references_section(text: str) -> str:
    """
    Cut everything from the last references/bibliography heading to end-of-text.

    We search from the end because the body may contain phrases like
    "as described in the References section" which we must not cut on.
    The *last* match is the actual references list.
    """
    matches = list(REFERENCE_SECTION_HEADINGS.finditer(text))
    if not matches:
        return text

    last_match = matches[-1]
    cut_pos = last_match.start()
    logger.debug(
        "Removing references section starting at char %d (heading: %r)",
        cut_pos,
        last_match.group().strip(),
    )
    return text[:cut_pos].rstrip()


def _collapse_blank_lines(text: str) -> str:
    """Reduce runs of more than 2 consecutive blank lines to exactly 2."""
    return re.sub(r"\n{3,}", "\n\n", text)


# ── Public API ────────────────────────────────────────────────────────────────


def clean_text(input_data: CleanerInput) -> CleanerOutput:
    """
    Run the full cleaning pipeline on raw source text.

    Steps applied in order:
      1. Normalize whitespace
      2. Remove page-number lines
      3. Remove repeated header/footer lines
      4. Remove references/bibliography section
      5. Collapse excessive blank lines

    Args:
        input_data: Validated CleanerInput with raw text, DOI, and evidence type.

    Returns:
        CleanerOutput with cleaned text and length statistics.
    """
    if input_data.evidence_availability.value == "ABSTRACT_AVAILABLE":
        logger.warning(
            "DOI %s — only abstract available; cleaning will still proceed but "
            "chunking context will be limited.",
            input_data.doi,
        )

    raw = input_data.raw_text
    original_length = len(raw)

    text = _normalize_whitespace(raw)
    text = _remove_page_numbers(text)
    text = _remove_repeated_lines(text)
    text = _remove_references_section(text)
    text = _collapse_blank_lines(text)
    text = text.strip()

    logger.info(
        "DOI %s — cleaned text: %d → %d chars (removed %d chars, %.1f%%)",
        input_data.doi,
        original_length,
        len(text),
        original_length - len(text),
        (1 - len(text) / original_length) * 100 if original_length else 0,
    )

    return CleanerOutput(
        clean_text=text,
        doi=input_data.doi,
        evidence_availability=input_data.evidence_availability,
        original_length=original_length,
        cleaned_length=len(text),
    )
