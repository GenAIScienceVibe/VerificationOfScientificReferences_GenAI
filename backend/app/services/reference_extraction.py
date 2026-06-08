from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.models import (
    ClaimCacheIndex,
    ClaimReferenceLink,
    Document,
    DocumentSection,
    EvidencePackage,
    RagRetrievalResult,
    Reference,
    SourceMetadata,
    UserFeedback,
    VerificationResult,
)
from app.models.enums import DocumentStatus, DoiStatus, MetadataStatus
from app.repositories import DocumentRepository, DocumentSectionRepository, ReferenceRepository
from app.services.text_processing import (
    is_post_reference_stop_heading_line,
    is_probable_pdf_artifact_line,
    is_reference_heading_line,
    repair_doi_line_continuations,
)

logger = logging.getLogger(__name__)

DOI_REGEX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
DOI_WITH_PREFIX_REGEX = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)
DOI_LIKE_REGEX = re.compile(r"(?:doi\s*[: ]\s*|doi\.org/|dx\.doi\.org/)?(10\.\S+)", re.IGNORECASE)
YEAR_REGEX = re.compile(r"\b((?:19|20)\d{2})(?:[a-z])?\b")

REFERENCE_HEADING_REGEX = re.compile(
    r"(?im)^\s*(references|bibliography|works\s+cited|reference\s+list|literatur|literaturverzeichnis)\s*[:.]?\s*$"
)
INLINE_REFERENCE_HEADING_REGEX = re.compile(
    r"(?im)^\s*(references|bibliography|works\s+cited|reference\s+list|literatur|literaturverzeichnis)\s*[:.]?\s+"
)

START_NUMBERED_REGEX = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+")
NUMBERED_AUTHOR_START_REGEX = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+[A-ZÀ-Þ]")
AUTHOR_YEAR_START_REGEX = re.compile(
    r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*(?:\s*,\s*[^.]{0,180})?\s*\((?:19|20)\d{2}[a-z]?\)",
    re.UNICODE,
)
AUTHOR_COMMA_YEAR_REGEX = re.compile(r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*){0,4}\s*,.{0,260}\b(?:19|20)\d{2}", re.UNICODE)

NOISE_MARKERS = (
    "welcome to the study",
    "employment status",
    "please state",
    "demographic questions",
    "ai tool usage",
    "screenout",
    "last page",
    "test510",
    "base page",
    "participant information",
    "thank you for participating",
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _normalized_reference_hash(raw_reference: str) -> str:
    normalized = re.sub(r"\s+", " ", raw_reference.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DoiExtractionResult:
    extracted_doi: str | None
    doi_status: str


@dataclass(frozen=True)
class ParsedReference:
    raw_reference: str
    reference_key: str
    extracted_title: str | None
    extracted_authors: str | None
    extracted_year: int | None
    extracted_doi: str | None
    doi_status: str
    normalized_raw_reference_hash: str


@dataclass(frozen=True)
class ReferenceSectionResult:
    text: str
    source: str


@dataclass(frozen=True)
class DoiCoverageReport:
    source_doi_count: int
    extracted_doi_count: int
    matched_doi_count: int
    missing_from_extracted: list[str]
    unexpected_extracted: list[str]
    coverage_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_doi_count": self.source_doi_count,
            "extracted_doi_count": self.extracted_doi_count,
            "matched_doi_count": self.matched_doi_count,
            "missing_from_extracted": self.missing_from_extracted,
            "unexpected_extracted": self.unexpected_extracted,
            "coverage_ratio": self.coverage_ratio,
        }


class ReferenceExtractionService:
    """Deterministic BE-4.1 reference and DOI extraction service.

    This service intentionally does not call CrossRef, OpenAlex, RAG, or GenAI.
    It performs local boundary cleanup, reference splitting, and DOI syntax extraction only.
    """

    def find_reference_section(self, *, cleaned_text: str | None, sections: list[DocumentSection]) -> ReferenceSectionResult:
        for section in sorted(sections, key=lambda item: item.order_index):
            if section.name and section.name.strip().lower() in {"references", "bibliography", "works cited", "reference list"}:
                if section.text and section.text.strip():
                    trimmed = self.trim_reference_section(section.text.strip())
                    if trimmed:
                        return ReferenceSectionResult(text=trimmed, source=f"DocumentSection:{section.name}")

        if not cleaned_text or not cleaned_text.strip():
            raise AppException(
                status_code=400,
                code=ErrorCode.DOCUMENT_TEXT_NOT_FOUND,
                field="document_id",
                detail="The document does not have cleaned text available for reference extraction.",
                message="Document text not found",
            )

        matches = list(REFERENCE_HEADING_REGEX.finditer(cleaned_text))
        inline_matches = [] if matches else list(INLINE_REFERENCE_HEADING_REGEX.finditer(cleaned_text))
        candidates = matches or inline_matches
        if not candidates:
            raise AppException(
                status_code=422,
                code=ErrorCode.REFERENCE_SECTION_NOT_FOUND,
                field="document_id",
                detail="No references section was found in the processed document.",
                message="Reference section not found",
            )

        # Prefer the last reference-like heading because references normally appear near the end.
        chosen = candidates[-1]
        reference_text = self.trim_reference_section(cleaned_text[chosen.end() :].strip())
        if not reference_text:
            raise AppException(
                status_code=422,
                code=ErrorCode.REFERENCE_SECTION_NOT_FOUND,
                field="document_id",
                detail="A references heading was found, but it did not contain usable reference text.",
                message="Reference section not found",
            )
        heading = chosen.group(1) if chosen.groups() else "references"
        return ReferenceSectionResult(text=reference_text, source=f"cleaned_text:{heading}")

    def trim_reference_section(self, text: str) -> str:
        repaired = repair_doi_line_continuations(text)
        kept: list[str] = []
        for line in repaired.replace("\r", "\n").split("\n"):
            stripped = line.strip()
            if not stripped:
                kept.append(line)
                continue
            if is_post_reference_stop_heading_line(stripped):
                break
            kept.append(line)
        return "\n".join(kept).strip()

    def split_references(self, reference_section_text: str) -> list[str]:
        normalized = repair_doi_line_continuations(reference_section_text.replace("\r\n", "\n").replace("\r", "\n")).strip()
        normalized = self._separate_doi_author_collisions(normalized)
        normalized = re.sub(r"[\t\f\v ]+", " ", normalized)
        if not normalized:
            return []

        lines = [line.strip() for line in normalized.split("\n")]
        lines = self._drop_heading_and_noise_lines(lines)
        chunks = self._chunk_reference_lines(lines)

        candidates: list[str] = []
        for chunk in chunks:
            for numbered_part in self._split_inline_numbered_references(chunk):
                candidates.extend(self._split_inline_author_year_references(numbered_part))

        merged: list[str] = []
        for candidate in (self._normalize_reference_text(item) for item in candidates):
            if not candidate:
                continue
            if self._is_continuation_fragment(candidate):
                if merged:
                    merged[-1] = self._normalize_reference_text(f"{merged[-1]} {candidate}")
                continue
            score = self._candidate_score(candidate)
            if self._is_reference_start(candidate) or score >= 3:
                merged.append(candidate)
            elif merged:
                # In ambiguous academic reference lists, appending is safer than creating
                # false rows. The later final DOI re-scan still detects any DOI that was
                # attached late.
                merged[-1] = self._normalize_reference_text(f"{merged[-1]} {candidate}")
            # else discard clear noise.
        return [item for item in merged if self._candidate_score(item) >= 3 or self.extract_doi(item).doi_status == DoiStatus.FOUND.value]

    def _separate_doi_author_collisions(self, text: str) -> str:
        # If an earlier conservative repair produced "...doi-fragment-Preacher, K.",
        # split before the next author surname rather than accepting the surname as DOI.
        return re.sub(
            r"(?i)(10\.\d{4,9}/[-._;()/:A-Z0-9]+[-/])([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*,\s+[A-Z](?:\.|[a-z]))",
            r"\1\n\2",
            text,
        )

    def _drop_heading_and_noise_lines(self, lines: list[str]) -> list[str]:
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append("")
                continue
            if is_reference_heading_line(stripped):
                continue
            if is_probable_pdf_artifact_line(stripped):
                continue
            if self._is_noise_line(stripped):
                continue
            cleaned.append(stripped)
        return cleaned

    def _chunk_reference_lines(self, lines: list[str]) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        for line in lines:
            if not line:
                if current:
                    chunks.append(" ".join(current).strip())
                    current = []
                continue

            is_start = self._is_reference_start(line)
            is_continuation = self._is_continuation_fragment(line)
            previous_line = current[-1].strip() if current else ""
            previous_continues_author_list = previous_line.endswith(("&", ",", ";")) or previous_line.endswith(", &")

            if current and is_start and not previous_continues_author_list:
                chunks.append(" ".join(current).strip())
                current = [line]
            else:
                if not current and is_continuation:
                    if chunks:
                        chunks[-1] = self._normalize_reference_text(f"{chunks[-1]} {line}")
                    else:
                        current = [line]
                    continue
                if current and is_continuation:
                    current.append(line)
                    continue
                current.append(line)
        if current:
            chunks.append(" ".join(current).strip())
        return chunks

    def _split_inline_numbered_references(self, text: str) -> list[str]:
        markers = list(re.finditer(r"(?<!\S)(?:\[\d+\]|\d+[.)])\s+(?=[A-ZÀ-Þ])", text))
        if len(markers) <= 1:
            return [text]
        parts: list[str] = []
        for index, marker in enumerate(markers):
            start = marker.start()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            part = text[start:end].strip()
            if part:
                parts.append(part)
        return parts

    def _split_inline_author_year_references(self, text: str) -> list[str]:
        # Split PDF-collapsed reference runs such as: "... doi. Alfarobi, I. (2024) ...".
        marker_regex = re.compile(
            r"(?<!^)(?<=\s)(?=[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*){0,4}\s*,[^()]{0,260}\((?:19|20)\d{2}[a-z]?\))",
            re.UNICODE,
        )
        markers = []
        for match in marker_regex.finditer(text):
            start = match.start()
            if start <= 8 and START_NUMBERED_REGEX.match(text):
                continue
            prefix_tail = text[max(0, start - 40) : start].strip()
            if prefix_tail.endswith(("&", ",", ";")) or prefix_tail.endswith(", &") or re.search(r"(?:,|&)\s*$", prefix_tail):
                continue
            prior = text[:start].strip()
            # Completed references can end in punctuation, a DOI/URL, or a broken DOI continuation dash.
            if prior and not re.search(r"(?:doi\.org/\S+|10\.\d{4,9}/\S+|[-.!?])\s*$", prior):
                continue
            markers.append(start)
        if not markers:
            return [text]
        starts = [0] + markers
        parts: list[str] = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(text)
            part = text[start:end].strip()
            if part:
                parts.append(part)
        return parts

    def _has_author_year_near_start(self, text: str) -> bool:
        first_segment = text[:340]
        doi_pos_candidates = [pos for pos in (first_segment.lower().find("doi.org/"), first_segment.lower().find("doi:"), first_segment.lower().find("10.")) if pos >= 0]
        doi_pos = min(doi_pos_candidates) if doi_pos_candidates else None
        year_match = YEAR_REGEX.search(first_segment)
        if not year_match:
            return False
        if doi_pos is not None and year_match.start() > doi_pos:
            return False
        if year_match.start() > 300:
            return False
        # Strong APA-like starts: Surname, A. ... (2023) or organization. (2025)
        if AUTHOR_YEAR_START_REGEX.match(first_segment):
            return True
        if re.match(r"^\s*(?:[A-Z]\.\s*){1,4},", first_segment):
            return True
        if re.match(r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*(?:\s+(?:de|den|der|van|von|del|da|di|le|la|[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*)){0,6}\s*,", first_segment):
            return True
        if re.match(r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*){0,6}\s*\([^)]*\)\.\s*\((?:19|20)\d{2}", first_segment):
            return True
        return False

    def _is_reference_start(self, line: str) -> bool:
        if self._is_noise_line(line):
            return False
        if NUMBERED_AUTHOR_START_REGEX.match(line) and self._has_author_year_near_start(START_NUMBERED_REGEX.sub("", line, count=1)):
            return True
        return self._has_author_year_near_start(line)

    def _is_noise_line(self, line: str) -> bool:
        stripped = line.strip()
        lowered = stripped.lower()
        if is_probable_pdf_artifact_line(stripped):
            return True
        if any(marker in lowered for marker in NOISE_MARKERS):
            return True
        # Do not drop DOI URLs: they are often continuation lines for the previous reference.
        if self._is_doi_only_or_doi_url_line(stripped):
            return False
        if re.fullmatch(r"(?:\d+[.)]\s*)?https?://\S+", stripped, re.IGNORECASE):
            return True
        if re.fullmatch(r"(?:\d+[.)]\s*)?(?:p-issn|e-issn).*", stripped, re.IGNORECASE):
            return True
        return False

    def _is_doi_only_or_doi_url_line(self, text: str) -> bool:
        stripped = text.strip()
        stripped = START_NUMBERED_REGEX.sub("", stripped, count=1).strip()
        return bool(
            re.fullmatch(r"(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)?10\.\d{4,9}/\S+", stripped, re.IGNORECASE)
            or re.fullmatch(r"https?://(?:dx\.)?doi\.org/10\.\d{4,9}/\S+", stripped, re.IGNORECASE)
        )

    def _looks_like_journal_or_volume_continuation(self, text: str) -> bool:
        stripped = text.strip()
        if self._is_reference_start(stripped):
            return False
        if len(stripped) < 8:
            return False
        # Common continuation lines begin with journal/book/source names, volume/issue/page data,
        # or a source title followed by a DOI/URL.
        if DOI_REGEX.search(stripped) or re.search(r"https?://(?:dx\.)?doi\.org/", stripped, re.IGNORECASE):
            if not re.match(r"^[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*\s*,\s+[A-Z]", stripped):
                return True
        if re.match(r"^(?:Journal|International|European|Frontiers|Psychology|Organizational|Artificial|Health|Information|Management|Computers|Education|MIS|BMC|Annual|Behavior|British|Telematics|Multidisciplinary)\b", stripped):
            return True
        if re.match(r"^[A-Z][A-Za-z &\-]+,\s*\d+(?:\([^)]+\))?,\s*\d+", stripped):
            return True
        return False

    def _is_continuation_fragment(self, text: str) -> bool:
        stripped = text.strip()
        if self._is_noise_line(stripped):
            return True
        if self._is_doi_only_or_doi_url_line(stripped):
            return True
        if self._looks_like_journal_or_volume_continuation(stripped):
            return True
        if re.fullmatch(r"[A-Za-z\s,]{1,40},\s*\d{1,4}\.?\s+https?://\S+", stripped, re.IGNORECASE):
            return True
        if DOI_REGEX.search(stripped) and not self._is_reference_start(stripped):
            return True
        return False

    def _candidate_score(self, text: str) -> int:
        score = 0
        if self._is_noise_line(text):
            return -5
        if AUTHOR_YEAR_START_REGEX.match(text) or AUTHOR_COMMA_YEAR_REGEX.match(text):
            score += 3
        if NUMBERED_AUTHOR_START_REGEX.match(text):
            score += 2
        if YEAR_REGEX.search(text):
            score += 1
        if DOI_REGEX.search(text):
            score += 1
        if len(text) > 40:
            score += 1
        if re.search(r"\.[\s\w\-]{8,}\.", text):
            score += 1
        if self._is_continuation_fragment(text):
            score -= 3
        return score

    def _normalize_reference_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def extract_doi(self, raw_reference: str) -> DoiExtractionResult:
        repaired = repair_doi_line_continuations(raw_reference)
        repaired = self._separate_doi_author_collisions(repaired)
        for match in DOI_WITH_PREFIX_REGEX.finditer(repaired):
            doi = self._normalize_doi(match.group(1))
            if self._looks_author_contaminated_doi(doi, repaired):
                return DoiExtractionResult(extracted_doi=None, doi_status=DoiStatus.MALFORMED.value)
            if self._is_syntactically_valid_doi(doi):
                return DoiExtractionResult(extracted_doi=doi, doi_status=DoiStatus.FOUND.value)
            if doi:
                return DoiExtractionResult(extracted_doi=doi, doi_status=DoiStatus.MALFORMED.value)

        if DOI_LIKE_REGEX.search(repaired) or re.search(
            r"(?:doi\s*[: ]\s*10\.|doi\s*[: ]\s*$|doi\.org/|dx\.doi\.org/|\b10\.)",
            repaired,
            re.IGNORECASE,
        ):
            return DoiExtractionResult(extracted_doi=None, doi_status=DoiStatus.MALFORMED.value)

        return DoiExtractionResult(extracted_doi=None, doi_status=DoiStatus.MISSING.value)

    def extract_doi_inventory(self, text: str) -> list[str]:
        repaired = repair_doi_line_continuations(text)
        repaired = self._separate_doi_author_collisions(repaired)
        found: list[str] = []
        seen: set[str] = set()
        for match in DOI_WITH_PREFIX_REGEX.finditer(repaired):
            doi = self._normalize_doi(match.group(1))
            if self._looks_author_contaminated_doi(doi, repaired):
                continue
            if self._is_syntactically_valid_doi(doi) and doi not in seen:
                seen.add(doi)
                found.append(doi)
        return found

    def build_doi_coverage_report(self, *, source_text: str, parsed_references: list[ParsedReference]) -> DoiCoverageReport:
        source_dois = self.extract_doi_inventory(source_text)
        extracted_dois = []
        for item in parsed_references:
            if item.doi_status == DoiStatus.FOUND.value and item.extracted_doi:
                extracted_dois.append(item.extracted_doi)
        extracted_unique = list(dict.fromkeys(extracted_dois))
        source_set = set(source_dois)
        extracted_set = set(extracted_unique)
        matched = sorted(source_set & extracted_set)
        missing = [doi for doi in source_dois if doi not in extracted_set]
        unexpected = [doi for doi in extracted_unique if doi not in source_set]
        ratio = round(len(matched) / len(source_dois), 4) if source_dois else 1.0
        return DoiCoverageReport(
            source_doi_count=len(source_dois),
            extracted_doi_count=len(extracted_unique),
            matched_doi_count=len(matched),
            missing_from_extracted=missing,
            unexpected_extracted=unexpected,
            coverage_ratio=ratio,
        )

    def _normalize_doi(self, value: str) -> str:
        doi = value.strip().strip("<>")
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)", "", doi, flags=re.IGNORECASE).strip()
        doi = doi.rstrip(",;")
        doi = doi.rstrip(".")
        while doi.endswith(")") and doi.count(")") > doi.count("("):
            doi = doi[:-1]
        doi = doi.strip().lower()
        return doi

    def _looks_author_contaminated_doi(self, doi: str, source_text: str) -> bool:
        if not doi or "-" not in doi:
            return False
        suffix = doi.rsplit("-", 1)[-1]
        if not re.fullmatch(r"[a-zà-ÿ'’]{3,30}", suffix, re.IGNORECASE):
            return False
        # If the candidate suffix appears as a surname followed by initials in the
        # same source text, it is almost certainly the next reference's author, not
        # a DOI suffix.
        return bool(re.search(rf"\b{re.escape(suffix)}\s*,\s*[A-Z]\.", source_text, re.IGNORECASE))

    def _is_syntactically_valid_doi(self, doi: str) -> bool:
        if not doi:
            return False
        if doi.endswith(("-", "/", ":")):
            return False
        suffix = doi.split("/", 1)[1] if "/" in doi else ""
        if len(suffix) < 3:
            return False
        return bool(re.fullmatch(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", doi))

    def parse_reference(self, raw_reference: str, index: int) -> ParsedReference:
        cleaned = self._normalize_reference_text(raw_reference)
        doi_result = self.extract_doi(cleaned)
        year = self._extract_year(cleaned)
        authors = self._extract_authors(cleaned)
        title = self._extract_title(cleaned)
        key = self._reference_key(authors=authors, year=year, index=index)
        return ParsedReference(
            raw_reference=cleaned,
            reference_key=key,
            extracted_title=title,
            extracted_authors=authors,
            extracted_year=year,
            extracted_doi=doi_result.extracted_doi,
            doi_status=doi_result.doi_status,
            normalized_raw_reference_hash=_normalized_reference_hash(cleaned),
        )

    def extract_references(self, reference_section_text: str) -> list[ParsedReference]:
        raw_references = self.split_references(reference_section_text)
        return [self.parse_reference(raw_reference, index=index) for index, raw_reference in enumerate(raw_references, start=1)]

    def _remove_leading_marker(self, text: str) -> str:
        return START_NUMBERED_REGEX.sub("", text, count=1).strip()

    def _extract_year(self, text: str) -> int | None:
        match = YEAR_REGEX.search(text)
        return int(match.group(1)) if match else None

    def _extract_authors(self, text: str) -> str | None:
        item = self._remove_leading_marker(text)
        match = re.match(r"^(.{2,300}?)\s*\((?:19|20)\d{2}[a-z]?\)", item)
        if not match:
            return None
        authors = match.group(1).strip().rstrip(".")
        return authors[:500] if authors else None

    def _extract_title(self, text: str) -> str | None:
        item = self._remove_leading_marker(text)
        after_year = re.split(r"\((?:19|20)\d{2}[a-z]?\)\.?\s*", item, maxsplit=1)
        if len(after_year) < 2:
            return None
        remainder = after_year[1].strip()
        remainder = re.split(r"\s+(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)", remainder, maxsplit=1, flags=re.IGNORECASE)[0]
        title_candidate = remainder.split(".")[0].strip(" .")
        if not title_candidate or len(title_candidate) < 3:
            return None
        return title_candidate[:1000]

    def _reference_key(self, *, authors: str | None, year: int | None, index: int) -> str:
        if not authors or not year:
            return f"Reference_{index:03d}"
        surnames = re.findall(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]*", authors)
        if not surnames:
            return f"Reference_{index:03d}"
        selected = surnames[:2]
        safe = "_".join(selected)
        safe = re.sub(r"[^A-Za-z0-9_\-]", "", safe)
        return f"{safe}_{year}" if safe else f"Reference_{index:03d}"


def reference_to_dict(reference: Reference) -> dict[str, Any]:
    return {
        "reference_id": reference.id,
        "document_id": reference.document_id,
        "reference_key": reference.reference_key,
        "raw_reference": reference.raw_reference,
        "extracted_title": reference.extracted_title,
        "extracted_authors": reference.extracted_authors,
        "extracted_year": reference.extracted_year,
        "extracted_doi": reference.extracted_doi,
        "doi_status": reference.doi_status,
        "metadata_status": reference.metadata_status,
        "metadata_match_score": reference.metadata_match_score,
        "created_at": _iso(reference.created_at),
        "updated_at": _iso(reference.updated_at),
        "phase": "BE-4.2",
        "is_stub": False,
    }


def _get_document_or_raise(document_id: str, db: Session) -> Document:
    document = DocumentRepository(db).get_with_sections(document_id)
    if not document:
        raise AppException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            field="document_id",
            detail=f"Document '{document_id}' was not found.",
            message="Document not found",
        )
    return document


def _has_downstream_reference_dependencies(document_id: str, db: Session) -> bool:
    reference_ids = list(db.scalars(select(Reference.id).where(Reference.document_id == document_id)).all())
    if not reference_ids:
        return False
    direct_counts = [
        db.scalar(select(func.count()).select_from(SourceMetadata).where(SourceMetadata.reference_id.in_(reference_ids))) or 0,
        db.scalar(select(func.count()).select_from(ClaimReferenceLink).where(ClaimReferenceLink.document_id == document_id)) or 0,
        db.scalar(select(func.count()).select_from(EvidencePackage).where(EvidencePackage.document_id == document_id)) or 0,
        db.scalar(select(func.count()).select_from(RagRetrievalResult).where(RagRetrievalResult.document_id == document_id)) or 0,
        db.scalar(select(func.count()).select_from(VerificationResult).where(VerificationResult.document_id == document_id)) or 0,
        db.scalar(select(func.count()).select_from(UserFeedback).where(UserFeedback.document_id == document_id)) or 0,
        db.scalar(select(func.count()).select_from(ClaimCacheIndex).where(ClaimCacheIndex.reference_id.in_(reference_ids))) or 0,
    ]
    return any(count > 0 for count in direct_counts)


def extract_references_for_document(document_id: str, db: Session, *, request_id: str | None = None) -> dict[str, Any]:
    document = _get_document_or_raise(document_id, db)
    logger.info("reference_extraction_start", extra={"document_id": document_id, "request_id": request_id})

    if _has_downstream_reference_dependencies(document_id, db):
        raise AppException(
            status_code=409,
            code=ErrorCode.REFERENCE_REEXTRACTION_BLOCKED,
            field="document_id",
            detail="Reference re-extraction is blocked because downstream metadata, mapping, evidence, verification, feedback, or cache rows already exist.",
            message="Reference re-extraction blocked",
        )

    sections = DocumentSectionRepository(db).list_for_document(document_id)
    service = ReferenceExtractionService()

    try:
        section_result = service.find_reference_section(cleaned_text=document.cleaned_text, sections=sections)
        parsed = service.extract_references(section_result.text)
        doi_coverage_report = service.build_doi_coverage_report(source_text=section_result.text, parsed_references=parsed)
    except AppException as exc:
        document.status = DocumentStatus.PARTIAL_FAILED.value
        db.commit()
        logger.warning(
            "reference_extraction_failed",
            extra={"document_id": document_id, "request_id": request_id, "error_code": exc.error.code},
        )
        raise

    if not parsed:
        document.status = DocumentStatus.PARTIAL_FAILED.value
        db.commit()
        logger.warning("reference_extraction_no_references", extra={"document_id": document_id, "request_id": request_id})
        raise AppException(
            status_code=422,
            code=ErrorCode.REFERENCE_EXTRACTION_FAILED,
            field="document_id",
            detail="A references section was found, but no individual references could be extracted.",
            message="Reference extraction failed",
        )

    document.status = DocumentStatus.REFERENCES_EXTRACTING.value
    db.commit()

    repo = ReferenceRepository(db)
    references = repo.replace_for_document(
        document_id=document_id,
        references=[
            {
                "reference_key": item.reference_key,
                "raw_reference": item.raw_reference,
                "extracted_title": item.extracted_title,
                "extracted_authors": item.extracted_authors,
                "extracted_year": item.extracted_year,
                "extracted_doi": item.extracted_doi,
                "doi_status": item.doi_status,
                "metadata_status": MetadataStatus.NOT_LOOKED_UP.value,
                "metadata_match_score": None,
            }
            for item in parsed
        ],
        commit=False,
    )
    document.references_count = len(references)
    document.status = DocumentStatus.REFERENCES_EXTRACTED.value
    db.commit()
    for reference in references:
        db.refresh(reference)
    db.refresh(document)

    doi_counts = Counter(reference.doi_status for reference in references)
    summary = {
        "found": doi_counts.get(DoiStatus.FOUND.value, 0),
        "missing": doi_counts.get(DoiStatus.MISSING.value, 0),
        "malformed": doi_counts.get(DoiStatus.MALFORMED.value, 0),
    }
    quality_warnings: list[str] = []
    if doi_coverage_report.source_doi_count >= 5 and doi_coverage_report.coverage_ratio < 0.85:
        quality_warnings.append("LOW_DOI_COVERAGE")
    if any((reference.extracted_doi or "").endswith("-") for reference in references if reference.doi_status == DoiStatus.FOUND.value):
        quality_warnings.append("BAD_FOUND_DOI_ENDING")
    logger.info(
        "reference_extraction_completed",
        extra={
            "document_id": document_id,
            "request_id": request_id,
            "references_count": len(references),
            "doi_summary": summary,
            "doi_coverage": doi_coverage_report.to_dict(),
            "quality_warnings": quality_warnings,
            "section_source": section_result.source,
        },
    )
    return {
        "document_id": document.id,
        "references_count": len(references),
        "doi_summary": summary,
        "doi_coverage": doi_coverage_report.to_dict(),
        "quality_warnings": quality_warnings,
        "status": document.status,
        "section_source": section_result.source,
        "phase": "BE-4.2",
        "is_stub": False,
        "processing_note": (
            "BE-4.2 deterministic reference extraction, DOI attachment, and DOI coverage diagnostics completed. DOI existence validation and metadata lookup are deferred to BE-5."
        ),
    }


def list_document_references(
    document_id: str,
    db: Session,
    *,
    doi_status: str | None = None,
    metadata_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _get_document_or_raise(document_id, db)
    references, total = ReferenceRepository(db).list_for_document_paginated(
        document_id=document_id,
        doi_status=doi_status,
        metadata_status=metadata_status,
        page=page,
        page_size=page_size,
    )
    return {
        "document_id": document_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "references": [reference_to_dict(reference) for reference in references],
        "phase": "BE-4.2",
        "processing_note": "References are parsed from the document text. Official metadata lookup is not performed until BE-5.",
    }


def get_reference(reference_id: str, db: Session) -> dict[str, Any]:
    reference = ReferenceRepository(db).get(reference_id)
    if not reference:
        raise AppException(
            status_code=404,
            code=ErrorCode.REFERENCE_NOT_FOUND,
            field="reference_id",
            detail=f"Reference '{reference_id}' was not found.",
            message="Reference not found",
        )
    return reference_to_dict(reference)
