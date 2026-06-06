from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectedSection:
    name: str
    order_index: int
    text: str
    text_preview: str
    page_start: int | None = None
    page_end: int | None = None


def clean_text(raw_text: str) -> str:
    """Clean extracted/submitted text without destroying citations, DOI strings, or reference lines."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    # Collapse horizontal whitespace but keep line breaks for headings/paragraphs.
    text = re.sub(r"[\t\f\v ]+", " ", text)
    # Merge conservative PDF line wraps: only join when both sides look like sentence content.
    text = re.sub(r"(?<=[a-z,;:])\n(?=[a-z(\[])", " ", text)
    # Keep paragraph/section boundaries readable.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _preview(text: str, limit: int = 500) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit]


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:512]
    return None


def detect_basic_sections(cleaned_text: str) -> list[DetectedSection]:
    """Rule-based BE-3 section detector.

    This intentionally does not split individual references or extract citations/DOIs.
    It only stores broad sections for BE-4 and later phases to consume.
    """
    text = cleaned_text.strip()
    if not text:
        return []

    heading_pattern = re.compile(
        r"(?im)^\s*(abstract|introduction|background|methods?|methodology|results?|discussion|conclusion|references|bibliography)\s*[:.]?\s*$"
    )
    matches = list(heading_pattern.finditer(text))
    sections: list[DetectedSection] = []

    # Title is a lightweight best effort: first non-empty line before the first heading.
    first_heading_start = matches[0].start() if matches else len(text)
    title_candidate = _first_non_empty_line(text[:first_heading_start]) or _first_non_empty_line(text)
    if title_candidate:
        sections.append(
            DetectedSection(
                name="Title",
                order_index=0,
                text=title_candidate,
                text_preview=_preview(title_candidate),
            )
        )

    if not matches:
        sections.append(
            DetectedSection(
                name="Body",
                order_index=len(sections),
                text=text,
                text_preview=_preview(text),
            )
        )
        return sections

    # Capture introductory content between title and first recognized heading as Body if meaningful.
    preface = text[: matches[0].start()].strip()
    if preface and preface != title_candidate and len(preface) > len(title_candidate or "") + 20:
        sections.append(
            DetectedSection(
                name="Body",
                order_index=len(sections),
                text=preface,
                text_preview=_preview(preface),
            )
        )

    for index, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = text[content_start:content_end].strip()
        if not section_text:
            continue
        if heading == "bibliography":
            normalized_name = "References"
        elif heading.startswith("method"):
            normalized_name = "Methods"
        elif heading.startswith("result"):
            normalized_name = "Results"
        elif heading == "background":
            normalized_name = "Body"
        else:
            normalized_name = heading.title()
        sections.append(
            DetectedSection(
                name=normalized_name,
                order_index=len(sections),
                text=section_text,
                text_preview=_preview(section_text),
            )
        )

    if not any(section.name == "References" for section in sections):
        # Keep a body fallback if headings consumed oddly.
        non_title_sections = [section for section in sections if section.name != "Title"]
        if not non_title_sections:
            sections.append(
                DetectedSection(
                    name="Body",
                    order_index=len(sections),
                    text=text,
                    text_preview=_preview(text),
                )
            )

    # Re-number after optional fallbacks.
    return [
        DetectedSection(
            name=section.name,
            order_index=index,
            text=section.text,
            text_preview=section.text_preview,
            page_start=section.page_start,
            page_end=section.page_end,
        )
        for index, section in enumerate(sections)
    ]
