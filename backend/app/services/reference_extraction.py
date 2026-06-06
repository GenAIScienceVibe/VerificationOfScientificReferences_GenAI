from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.models import Document, DocumentSection, Reference
from app.models.enums import DocumentStatus, DoiStatus, MetadataStatus
from app.repositories import DocumentRepository, DocumentSectionRepository, ReferenceRepository

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
STOP_AFTER_REFERENCES_REGEX = re.compile(
    r"(?im)^\s*(appendix|appendices|supplementary\s+material|supplemental\s+material|acknowledgements?|acknowledgments?)\s*[:.]?\s*$"
)

START_NUMBERED_REGEX = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+")
AUTHOR_YEAR_START_REGEX = re.compile(
    r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s*,\s*[^.]{0,120})?\s*\((?:19|20)\d{2}[a-z]?\)",
    re.UNICODE,
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


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


@dataclass(frozen=True)
class ReferenceSectionResult:
    text: str
    source: str


class ReferenceExtractionService:
    """Deterministic BE-4 reference and DOI extraction service.

    This service intentionally does not call CrossRef, OpenAlex, RAG, or GenAI.
    BE-4 only performs rule-based reference splitting and DOI syntax extraction.
    """

    def find_reference_section(self, *, cleaned_text: str | None, sections: list[DocumentSection]) -> ReferenceSectionResult:
        for section in sorted(sections, key=lambda item: item.order_index):
            if section.name and section.name.strip().lower() in {"references", "bibliography", "works cited", "reference list"}:
                if section.text and section.text.strip():
                    return ReferenceSectionResult(text=section.text.strip(), source=f"DocumentSection:{section.name}")

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
        if not matches and not inline_matches:
            raise AppException(
                status_code=422,
                code=ErrorCode.REFERENCE_SECTION_NOT_FOUND,
                field="document_id",
                detail="No references section was found in the processed document.",
                message="Reference section not found",
            )

        # Prefer the last reference-like heading because references normally appear near the end.
        chosen = (matches or inline_matches)[-1]
        content_start = chosen.end()
        stop_match = STOP_AFTER_REFERENCES_REGEX.search(cleaned_text, pos=content_start)
        content_end = stop_match.start() if stop_match else len(cleaned_text)
        reference_text = cleaned_text[content_start:content_end].strip()
        if not reference_text:
            raise AppException(
                status_code=422,
                code=ErrorCode.REFERENCE_SECTION_NOT_FOUND,
                field="document_id",
                detail="A references heading was found, but it did not contain usable reference text.",
                message="Reference section not found",
            )
        return ReferenceSectionResult(text=reference_text, source=f"cleaned_text:{chosen.group(1)}")

    def split_references(self, reference_section_text: str) -> list[str]:
        normalized = reference_section_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = re.sub(r"[\t\f\v ]+", " ", normalized)
        if not normalized:
            return []

        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n+", normalized) if chunk.strip()]
        references: list[str] = []
        for chunk in chunks:
            references.extend(self._split_chunk_by_reference_starts(chunk))

        # If a PDF collapsed numbered references into one paragraph, split by inline numbering markers.
        expanded: list[str] = []
        for reference in references:
            inline_parts = self._split_inline_numbered_references(reference)
            expanded.extend(inline_parts if len(inline_parts) > 1 else [reference])

        cleaned_refs = [self._normalize_reference_text(item) for item in expanded]
        return [item for item in cleaned_refs if self._looks_like_reference(item)]

    def _split_chunk_by_reference_starts(self, chunk: str) -> list[str]:
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            return []

        refs: list[str] = []
        current: list[str] = []
        for line in lines:
            is_start = self._is_reference_start(line)
            if current and is_start:
                refs.append(" ".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            refs.append(" ".join(current).strip())
        return refs

    def _split_inline_numbered_references(self, text: str) -> list[str]:
        markers = list(re.finditer(r"(?<!\S)(?:\[\d+\]|\d+[.)])\s+", text))
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

    def _is_reference_start(self, line: str) -> bool:
        if START_NUMBERED_REGEX.match(line):
            return True
        if AUTHOR_YEAR_START_REGEX.match(line):
            return True
        # APA entries often start with author text and place the year within the first segment.
        first_segment = line[:180]
        return bool(re.match(r"^\s*[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+\s*,", first_segment) and YEAR_REGEX.search(first_segment))

    def _normalize_reference_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _looks_like_reference(self, text: str) -> bool:
        if len(text) < 12:
            return False
        return bool(YEAR_REGEX.search(text) or DOI_REGEX.search(text) or START_NUMBERED_REGEX.match(text))

    def extract_doi(self, raw_reference: str) -> DoiExtractionResult:
        match = DOI_WITH_PREFIX_REGEX.search(raw_reference)
        if match:
            doi = self._normalize_doi(match.group(1))
            if self._is_syntactically_valid_doi(doi):
                return DoiExtractionResult(extracted_doi=doi, doi_status=DoiStatus.FOUND.value)
            return DoiExtractionResult(extracted_doi=doi or None, doi_status=DoiStatus.MALFORMED.value)

        # Only classify as malformed when the text contains a DOI-like marker/prefix or a broken 10.* value.
        # A sentence like "without a DOI" should be treated as MISSING, not MALFORMED.
        if DOI_LIKE_REGEX.search(raw_reference) or re.search(
            r"(?:doi\s*[: ]\s*10\.|doi\s*[: ]\s*$|doi\.org/|dx\.doi\.org/|\b10\.)",
            raw_reference,
            re.IGNORECASE,
        ):
            return DoiExtractionResult(extracted_doi=None, doi_status=DoiStatus.MALFORMED.value)

        return DoiExtractionResult(extracted_doi=None, doi_status=DoiStatus.MISSING.value)

    def _normalize_doi(self, value: str) -> str:
        doi = value.strip().strip("<>")
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)", "", doi, flags=re.IGNORECASE).strip()
        # Remove obvious sentence punctuation while preserving valid balanced parentheses inside DOI strings.
        doi = doi.rstrip(".,;")
        while doi.endswith(")") and doi.count(")") > doi.count("("):
            doi = doi[:-1]
        doi = doi.strip().lower()
        return doi

    def _is_syntactically_valid_doi(self, doi: str) -> bool:
        if not doi:
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
        # Prefer author segment before APA-style year parentheses.
        match = re.match(r"^(.{2,240}?)\s*\((?:19|20)\d{2}[a-z]?\)", item)
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
        # Stop before DOI/URL when possible.
        remainder = re.split(r"\s+(?:https?://doi\.org/|http://dx\.doi\.org/|doi\s*[: ]\s*)", remainder, maxsplit=1, flags=re.IGNORECASE)[0]
        title_candidate = remainder.split(".")[0].strip(" .")
        if not title_candidate or len(title_candidate) < 3:
            return None
        return title_candidate[:1000]

    def _reference_key(self, *, authors: str | None, year: int | None, index: int) -> str:
        if not authors or not year:
            return f"Reference_{index:03d}"
        surnames = re.findall(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+", authors)
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
        "phase": "BE-4",
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


def extract_references_for_document(document_id: str, db: Session, *, request_id: str | None = None) -> dict[str, Any]:
    document = _get_document_or_raise(document_id, db)
    logger.info("reference_extraction_start", extra={"document_id": document_id, "request_id": request_id})

    sections = DocumentSectionRepository(db).list_for_document(document_id)
    service = ReferenceExtractionService()

    try:
        section_result = service.find_reference_section(cleaned_text=document.cleaned_text, sections=sections)
        parsed = service.extract_references(section_result.text)
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
    logger.info(
        "reference_extraction_completed",
        extra={
            "document_id": document_id,
            "request_id": request_id,
            "references_count": len(references),
            "doi_summary": summary,
            "section_source": section_result.source,
        },
    )
    return {
        "document_id": document.id,
        "references_count": len(references),
        "doi_summary": summary,
        "status": document.status,
        "section_source": section_result.source,
        "phase": "BE-4",
        "is_stub": False,
        "processing_note": (
            "BE-4 deterministic reference and DOI extraction completed. DOI existence validation and metadata lookup are deferred to BE-5."
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
        "phase": "BE-4",
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
