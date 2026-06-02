"""
BE-2 GenAI Section Detection Service
--------------------------------------
Uses Claude to detect document sections from extracted text.
Falls back to regex-based detection if API is unavailable.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

import anthropic

from app.logger import logger
from app.db.models import SectionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _type_to_name(t: SectionType) -> str:
    return {
        SectionType.title: "Title",
        SectionType.abstract: "Abstract",
        SectionType.introduction: "Introduction",
        SectionType.body: "Body",
        SectionType.references: "References",
        SectionType.unknown: "Content",
    }.get(t, "Content")


def _str_to_section_type(s: str) -> SectionType:
    mapping = {
        "title": SectionType.title,
        "abstract": SectionType.abstract,
        "introduction": SectionType.introduction,
        "body": SectionType.body,
        "methods": SectionType.body,
        "results": SectionType.body,
        "discussion": SectionType.body,
        "conclusion": SectionType.body,
        "references": SectionType.references,
        "bibliography": SectionType.references,
        "acknowledgments": SectionType.references,
    }
    return mapping.get(s.lower().strip(), SectionType.unknown)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field

@dataclass
class DetectedSection:
    name: str
    type: SectionType
    order_index: int
    full_text: str
    start_char: int
    end_char: int

    @property
    def text_preview(self) -> str:
        return self.full_text[:200].strip()


# ---------------------------------------------------------------------------
# GenAI detection
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a scientific document analyzer.
Your task is to identify section headers from a list of candidate lines extracted from an academic paper.

You will receive a list of candidate lines that might be section headers.
Return ONLY a valid JSON array. No explanation, no markdown, no code blocks.

Each item must have:
- "name": the section name (e.g. "Abstract", "1. Introduction", "Methods")
- "type": one of: title, abstract, introduction, body, references
- "header_text": the exact line from the candidates list

Use these type rules:
- title: paper title (usually first, longest, no number prefix)
- abstract: abstract or summary
- introduction: introduction section
- body: methods, results, discussion, conclusion, findings, data, adoption, beliefs, experiment, evaluation, background, related work, or any numbered section
- references: references, bibliography, acknowledgments, data availability

Only include lines that are genuine section headers. Skip page numbers, figure captions, author names.

Example output:
[
  {"name": "Abstract", "type": "abstract", "header_text": "Abstract"},
  {"name": "1. Introduction", "type": "introduction", "header_text": "1. Introduction"},
  {"name": "2. Methods", "type": "body", "header_text": "2. Methods"},
  {"name": "References", "type": "references", "header_text": "References"}
]"""


def _extract_candidate_lines(text: str) -> List[str]:
    """
    Extract lines that could be section headers:
    - Short lines (< 80 chars)
    - Start with a number or known keyword
    - Not purely numeric (page numbers)
    - Appear at start of paragraph
    """
    candidates = []
    seen = set()

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()

        # Skip empty, too long, or pure numbers
        if not stripped or len(stripped) > 80 or stripped.isdigit():
            continue

        # Skip lines that look like citations [1] or footnotes
        if re.match(r"^\[\d+\]", stripped):
            continue

        # Include if starts with number+dot (section header pattern)
        if re.match(r"^\d+\.?\s+\w", stripped):
            if stripped not in seen:
                candidates.append(stripped)
                seen.add(stripped)
            continue

        # Include known keywords
        keywords = [
            "abstract", "summary", "introduction", "background",
            "methods", "materials", "results", "discussion",
            "conclusion", "findings", "references", "bibliography",
            "acknowledgments", "appendix", "related work",
            "data availability", "significance",
        ]
        lower = stripped.lower()
        if any(lower.startswith(k) for k in keywords):
            if stripped not in seen:
                candidates.append(stripped)
                seen.add(stripped)

    return candidates[:50]  # max 50 candidates


def detect_sections_with_genai(cleaned_text: str, raw_text: Optional[str] = None) -> Optional[List[DetectedSection]]:
    """
    Use Claude to detect sections using a two-stage approach:
    1. Extract candidate header lines from raw_text (before line-joining)
    2. Send only those candidates to Claude to classify
    Works for papers of any length.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("[section_detection] ANTHROPIC_API_KEY not set — skipping GenAI detection")
        return None

    # Stage 1: Extract candidates from raw_text (has original line breaks)
    # Fall back to cleaned_text if raw_text not available
    source_for_candidates = raw_text if raw_text else cleaned_text
    candidates = _extract_candidate_lines(source_for_candidates)
    if not candidates:
        logger.warning("[section_detection] No candidate lines found — skipping GenAI detection")
        return None

    candidates_text = "\n".join(f"- {c}" for c in candidates)
    logger.info(f"[section_detection] Sending {len(candidates)} candidates to Claude")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Identify which of these lines are genuine section headers "
                        f"from an academic paper:\n\n{candidates_text}"
                    ),
                }
            ],
        )

        raw = message.content[0].text.strip()
        logger.info(f"[section_detection] GenAI response: {raw[:300]}")

        sections_json = json.loads(raw)
        if not isinstance(sections_json, list):
            raise ValueError("Expected a JSON array")

        # Build DetectedSection objects by finding positions in full text
        result: List[DetectedSection] = []
        order_index = 0

        # Add title as first section (text before first detected header)
        first_header_pos = len(cleaned_text)
        if sections_json:
            first_header = sections_json[0].get("header_text", "").strip()
            if first_header:
                pos = cleaned_text.find(first_header)
                if pos != -1:
                    first_header_pos = pos

        title_text = cleaned_text[:first_header_pos].strip()
        if title_text:
            result.append(DetectedSection(
                name="Title",
                type=SectionType.title,
                order_index=order_index,
                full_text=title_text,
                start_char=0,
                end_char=first_header_pos,
            ))
            order_index += 1

        # Add detected sections
        for i, sec in enumerate(sections_json):
            name = sec.get("name", "Content")
            sec_type = _str_to_section_type(sec.get("type", "unknown"))
            header = sec.get("header_text", "").strip()

            if not header:
                continue

            start = cleaned_text.find(header)
            if start == -1:
                continue

            # End = start of next section
            if i + 1 < len(sections_json):
                next_header = sections_json[i + 1].get("header_text", "").strip()
                next_pos = cleaned_text.find(next_header, start + 1) if next_header else -1
                end = next_pos if next_pos != -1 else len(cleaned_text)
            else:
                end = len(cleaned_text)

            full_text = cleaned_text[start:end].strip()
            if not full_text:
                continue

            result.append(DetectedSection(
                name=name,
                type=sec_type,
                order_index=order_index,
                full_text=full_text,
                start_char=start,
                end_char=end,
            ))
            order_index += 1

        logger.info(f"[section_detection] GenAI detected {len(result)} sections: {[s.type.value for s in result]}")
        return result if result else None

    except json.JSONDecodeError as e:
        logger.error(f"[section_detection] Failed to parse GenAI JSON response: {e} — raw: {raw[:200]}")
        return None
    except Exception as e:
        logger.error(f"[section_detection] GenAI call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

_FALLBACK_PATTERNS = {
    SectionType.abstract: [
        r"^\s*abstract\s*$",
        r"^\s*summary\s*$",
    ],
    SectionType.introduction: [
        r"^\s*\d*\.?\s*introduction\s*$",
        r"^\s*background\s*$",
    ],
    SectionType.body: [
        r"^\s*\d+\.?\s*materials?\s+and\s+methods?\s*$",
        r"^\s*\d+\.?\s*methods?\s*$",
        r"^\s*\d+\.?\s*results?\s*$",
        r"^\s*\d+\.?\s*discussion\s*$",
        r"^\s*\d+\.?\s*conclusion\s*$",
        r"^\s*\d+\.?\s*adoption\s+of\s+\w[\w\s]*$",
        r"^\s*\d+\.?\s*beliefs?\s*(vs\.?\s*(adoption|use))?\s*$",
    ],
    SectionType.references: [
        r"^\s*references?\s*$",
        r"^\s*bibliography\s*$",
        r"^\s*acknowledgments?\s*$",
        r"^\s*data,?\s*materials?,?\s*(and\s+)?software\s*.*$",
    ],
}


def detect_sections_regex_fallback(cleaned_text: str) -> List[DetectedSection]:
    """Simple regex-based section detection as fallback."""
    paragraphs = cleaned_text.split("\n\n")
    sections: List[DetectedSection] = []
    current_type = SectionType.unknown
    current_name = "Content"
    current_parts: List[str] = []
    order_index = 0
    char_offset = 0
    section_start = 0

    # First paragraph → title
    title_text = ""
    start_idx = 0
    for i, para in enumerate(paragraphs):
        if para.strip():
            title_text = para.strip()
            start_idx = i + 1
            break

    if title_text:
        sections.append(DetectedSection(
            name="Title", type=SectionType.title, order_index=order_index,
            full_text=title_text, start_char=0, end_char=len(title_text),
        ))
        char_offset = len(title_text) + 2
        order_index += 1

    section_start = char_offset

    def _flush():
        nonlocal order_index
        text = "\n\n".join(current_parts).strip()
        if text:
            sections.append(DetectedSection(
                name=current_name, type=current_type, order_index=order_index,
                full_text=text, start_char=section_start,
                end_char=section_start + len(text),
            ))
            order_index += 1

    for para in paragraphs[start_idx:]:
        detected = None
        stripped = para.strip()
        if stripped and len(stripped) < 80:
            for s_type, patterns in _FALLBACK_PATTERNS.items():
                for pattern in patterns:
                    if re.match(pattern, stripped, re.IGNORECASE):
                        detected = s_type
                        break
                if detected:
                    break

        if detected is not None:
            _flush()
            current_parts.clear()
            current_type = detected
            current_name = stripped
            section_start = char_offset + len(para) + 2
        else:
            current_parts.append(para)

        char_offset += len(para) + 2

    _flush()

    if len(sections) <= 1:
        return [
            DetectedSection(name="Title", type=SectionType.title, order_index=0,
                            full_text=title_text, start_char=0, end_char=len(title_text)),
            DetectedSection(name="Body", type=SectionType.body, order_index=1,
                            full_text=cleaned_text[len(title_text):].strip(),
                            start_char=len(title_text), end_char=len(cleaned_text)),
        ]

    return sections


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_sections(cleaned_text: str, raw_text: Optional[str] = None) -> List[DetectedSection]:
    """
    Detect sections using GenAI first, fallback to regex if unavailable.
    raw_text is used for candidate extraction (headers visible before line-joining).
    """
    # Try GenAI first
    result = detect_sections_with_genai(cleaned_text, raw_text=raw_text)
    if result:
        return result

    # Fallback to regex
    logger.info("[section_detection] Using regex fallback for section detection")
    return detect_sections_regex_fallback(cleaned_text)
