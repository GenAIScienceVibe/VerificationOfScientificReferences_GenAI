from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.models import Document, DocumentSection

EXCLUDED_SECTION_NAMES = {
    "references",
    "bibliography",
    "works cited",
    "reference list",
    "literatur",
    "literaturverzeichnis",
    "appendix",
    "appendices",
    "supplementary material",
}

PREFERRED_BODY_SECTION_NAMES = {
    "abstract",
    "introduction",
    "literature review",
    "background",
    "theoretical background",
    "methodology",
    "methods",
    "results",
    "discussion",
    "body",
    "main content",
    "conclusion",
}

REFERENCE_HEADING_RE = re.compile(
    r"(?im)^\s*(references|bibliography|works\s+cited|reference\s+list|literatur|literaturverzeichnis)\s*[:.]?\s*$"
)

APA_PARENTHETICAL_RE = re.compile(
    r"\([^)]*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+[^)]*,\s*(?:19|20)\d{2}[a-z]?[^)]*\)",
    re.UNICODE,
)
APA_NARRATIVE_RE = re.compile(
    r"\b[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s+(?:and|&)\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+|\s+et\s+al\.)?\s*\((?:19|20)\d{2}[a-z]?\)",
    re.UNICODE,
)
BRACKET_NUMERIC_RE = re.compile(r"\[(?:\d{1,3})(?:\s*(?:,|-|–)\s*\d{1,3})*\]")
PAREN_NUMERIC_RE = re.compile(r"(?<![A-Za-z0-9])\((?:\d{1,3})(?:\s*(?:,|-|–)\s*\d{1,3})*\)(?![A-Za-z0-9])")
SUPERSCRIPT_LIKE_RE = re.compile(r"(?<!\w)\^(\d{1,3})(?!\w)")


@dataclass(frozen=True)
class DetectedCitation:
    citation_text: str
    citation_style: str
    start: int
    end: int


@dataclass(frozen=True)
class PreparedSentence:
    paragraph_key: str
    section_name: str
    paragraph_index: int
    sentence_index: int
    sentence_text: str
    source_paragraph: str
    detected_citations: list[DetectedCitation] = field(default_factory=list)


class CitationDetectionService:
    """Deterministic BE-6 citation detector.

    It intentionally preserves citation text exactly as found in the source sentence.
    """

    def detect(self, text: str) -> list[DetectedCitation]:
        matches: list[DetectedCitation] = []
        for regex, style in (
            (APA_PARENTHETICAL_RE, "APA"),
            (APA_NARRATIVE_RE, "APA"),
            (BRACKET_NUMERIC_RE, "NUMBERED"),
            (PAREN_NUMERIC_RE, "NUMBERED"),
            (SUPERSCRIPT_LIKE_RE, "NUMBERED"),
        ):
            for match in regex.finditer(text):
                citation_text = match.group(0)
                if style == "NUMBERED" and citation_text.startswith("("):
                    # Avoid treating common statistical values or years as citations.
                    inner = citation_text.strip("()")
                    if len(inner) == 4 and inner.startswith(("19", "20")):
                        continue
                matches.append(DetectedCitation(citation_text=citation_text, citation_style=style, start=match.start(), end=match.end()))
        matches.sort(key=lambda item: (item.start, item.end))
        deduped: list[DetectedCitation] = []
        seen: set[tuple[int, int, str]] = set()
        for item in matches:
            key = (item.start, item.end, item.citation_text)
            if key not in seen:
                deduped.append(item)
                seen.add(key)
        return deduped


class ClaimPreparationService:
    """Prepares body-only citation-bearing sentences for claim extraction."""

    def __init__(self, citation_detector: CitationDetectionService | None = None) -> None:
        self.citation_detector = citation_detector or CitationDetectionService()

    def prepare(self, document: Document, sections: Iterable[DocumentSection]) -> list[PreparedSentence]:
        body_sections = self._select_body_sections(document, list(sections))
        prepared: list[PreparedSentence] = []
        paragraph_index = 0
        for section_name, section_text in body_sections:
            for paragraph in self._split_paragraphs(section_text):
                if len(paragraph) < 35:
                    continue
                sentence_index = 0
                paragraph_key = f"p_{paragraph_index:04d}"
                for sentence in self._split_sentences(paragraph):
                    citations = self.citation_detector.detect(sentence)
                    if citations:
                        prepared.append(
                            PreparedSentence(
                                paragraph_key=paragraph_key,
                                section_name=section_name,
                                paragraph_index=paragraph_index,
                                sentence_index=sentence_index,
                                sentence_text=sentence,
                                source_paragraph=paragraph,
                                detected_citations=citations,
                            )
                        )
                    sentence_index += 1
                paragraph_index += 1
        return prepared

    def _select_body_sections(self, document: Document, sections: list[DocumentSection]) -> list[tuple[str, str]]:
        usable: list[tuple[str, str]] = []
        for section in sorted(sections, key=lambda item: item.order_index):
            name = (section.name or "Body").strip()
            lowered = name.lower()
            if lowered in EXCLUDED_SECTION_NAMES or lowered.startswith("appendix"):
                continue
            text = section.text or ""
            if text.strip():
                usable.append((name, text))
        if usable:
            return usable
        cleaned = document.cleaned_text or document.raw_text or ""
        return [("Body", self._remove_reference_tail(cleaned))] if cleaned.strip() else []

    def _remove_reference_tail(self, text: str) -> str:
        matches = list(REFERENCE_HEADING_RE.finditer(text))
        if not matches:
            return text
        return text[: matches[-1].start()].strip()

    def _split_paragraphs(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        parts = re.split(r"\n\s*\n+", normalized)
        if len(parts) <= 1:
            parts = re.split(r"(?<=\.)\s{2,}(?=[A-ZÀ-Þ0-9])", normalized)
        return [re.sub(r"\s+", " ", part).strip() for part in parts if part and part.strip()]

    def _split_sentences(self, paragraph: str) -> list[str]:
        # Keeps citations with their sentence and avoids common abbreviation splits enough for MVP.
        protected = paragraph
        abbreviations = {"et al.": "et al§", "e.g.": "e§g§", "i.e.": "i§e§", "Dr.": "Dr§", "Prof.": "Prof§"}
        for raw, repl in abbreviations.items():
            protected = protected.replace(raw, repl)
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Þ0-9\[])", protected)
        sentences = []
        for part in parts:
            for raw, repl in abbreviations.items():
                part = part.replace(repl, raw)
            cleaned = part.strip()
            if cleaned:
                sentences.append(cleaned)
        return sentences or [paragraph.strip()]
