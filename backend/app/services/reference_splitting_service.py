"""
BE-3 GenAI Reference Splitting Service
----------------------------------------
Uses Claude to split a reference section into individual references.
Falls back to regex-based splitting if API is unavailable.
Works for any citation style: numbered, Harvard, APA, Vancouver, IEEE, etc.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

import anthropic

from app.logger import logger


SYSTEM_PROMPT = """You are a scientific reference parser.
You will receive the references section of an academic paper.
Your task is to split it into individual references.

Return ONLY a valid JSON array of strings. No explanation, no markdown, no code blocks.
Each string is one complete reference entry.

Rules:
- Each reference is one item in the array
- Keep the full text of each reference including authors, title, journal, year, DOI etc.
- Do not modify or truncate any reference
- Skip section headers like "References", "Bibliography", "Acknowledgments"
- Skip page numbers, figure captions, or other non-reference content

Example output:
[
  "Smith, J., Doe, A., 2020. Title of paper. Journal Name 10 (2), 100-110. https://doi.org/10.1000/xyz",
  "Jones, E., 2019. Another paper title. Conference Proceedings. pp. 50-60.",
  "1. Brown, K. et al. Third reference. Science 384, 1306-1308 (2024)."
]"""


def split_references_with_genai(ref_section_text: str) -> Optional[List[str]]:
    """
    Use Claude to split a reference section into individual references.
    Returns None if API call fails.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("[ref_splitting] ANTHROPIC_API_KEY not set — skipping GenAI splitting")
        return None

    if len(ref_section_text.strip()) < 50:
        logger.warning("[ref_splitting] Reference section too short — skipping GenAI splitting")
        return None

    # Cap at 8000 chars — enough for ~30-40 references
    text_sample = ref_section_text[:8000]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Split these references into individual entries:\n\n{text_sample}",
                }
            ],
        )

        raw = message.content[0].text.strip()
        logger.info(f"[ref_splitting] GenAI response preview: {raw[:200]}")

        refs = json.loads(raw)
        if not isinstance(refs, list):
            raise ValueError("Expected a JSON array")

        # Filter out empty strings and very short entries
        refs = [r.strip() for r in refs if isinstance(r, str) and len(r.strip()) > 20]

        logger.info(f"[ref_splitting] GenAI split into {len(refs)} references")
        return refs

    except json.JSONDecodeError as e:
        logger.error(f"[ref_splitting] Failed to parse GenAI JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"[ref_splitting] GenAI call failed: {e}")
        return None


def split_references_regex(ref_section_text: str) -> List[str]:
    """
    Regex-based reference splitting as fallback.
    Handles: numbered (1. / [1]), Harvard, paragraph-based.
    """
    text = ref_section_text.strip()

    # Remove header line
    for header in ["References", "Bibliography", "Works Cited", "Literatur", "Referenzen"]:
        if text.lower().startswith(header.lower()):
            text = text[len(header):].strip()

    # Numbered: 1. / [1] / 1)
    numbered = re.compile(r'(?m)^(\d+[\.\)]\s+|\[\d+\]\s*)', re.MULTILINE)
    matches = list(numbered.finditer(text))
    if len(matches) >= 2:
        refs = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            ref = text[start:end].strip()
            if len(ref) > 20:
                refs.append(ref)
        if refs:
            return refs

    # Bracketed: [Smith2020]
    bracketed = re.compile(r'(?m)^\[[\w\d,\s]+\]\s+', re.MULTILINE)
    matches = list(bracketed.finditer(text))
    if len(matches) >= 2:
        refs = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            ref = text[start:end].strip()
            if len(ref) > 20:
                refs.append(ref)
        if refs:
            return refs

    # Harvard: lines starting with Author, Initial.
    harvard = re.compile(
        r'(?m)^([A-Z][a-z]+,\s+[A-Z][\w.]*|[A-Z][a-z]+\s+[A-Z][a-z]+,)',
        re.MULTILINE,
    )
    matches = list(harvard.finditer(text))
    if len(matches) >= 3:
        refs = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            ref = text[start:end].strip()
            if len(ref) > 20:
                refs.append(ref)
        if len(refs) >= 3:
            return refs

    # Paragraph-based fallback
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text)]
    refs = [p for p in paragraphs if len(p) > 20]
    if refs:
        return refs

    # Last resort: line by line
    return [l.strip() for l in text.split('\n') if len(l.strip()) > 20]


def split_references(ref_section_text: str) -> List[str]:
    """
    Split references using GenAI first, fallback to regex.
    Works for any citation style.
    """
    result = split_references_with_genai(ref_section_text)
    if result:
        return result

    logger.info("[ref_splitting] Using regex fallback for reference splitting")
    return split_references_regex(ref_section_text)
