"""
BE-3 Reference Extraction Service
-----------------------------------
Handles:
  - Splitting reference section into individual references
  - DOI extraction via regex
  - DOI normalization
  - DOI status detection: FOUND, MISSING, MALFORMED
  - Storing references in DB
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentProcessingStatus,
    DocumentSection,
    DoiStatus,
    MetadataStatus,
    Reference,
    SectionType,
)
from app.db.repositories import (
    DocumentRepository,
    DocumentSectionRepository,
    ReferenceRepository,
)
from app.logger import logger
from app.services.reference_splitting_service import split_references


# ---------------------------------------------------------------------------
# DOI patterns
# ---------------------------------------------------------------------------

# Standard DOI pattern: 10.XXXX/anything
_DOI_PATTERN = re.compile(
    r'\b(10\.\d{4,9}/[^\s\]\[,;\'\"<>]+)',
    re.IGNORECASE,
)

# DOI URL prefix patterns to strip
_DOI_URL_PREFIXES = [
    r'^https?://doi\.org/',
    r'^https?://dx\.doi\.org/',
    r'^doi:',
    r'^DOI:',
]

# Malformed DOI: starts with 10. but has invalid format
_MALFORMED_DOI_PATTERN = re.compile(
    r'\b10\.[^\s/]{0,3}(?:/\S*)?',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Reference splitting
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DOI extraction + normalization
# ---------------------------------------------------------------------------

def extract_doi(text: str) -> Tuple[Optional[str], DoiStatus]:
    """
    Extract and normalize DOI from reference text.
    Returns (doi_normalized, doi_status).
    """
    # Search for DOI pattern
    match = _DOI_PATTERN.search(text)

    if match:
        raw_doi = match.group(1)

        # Strip trailing punctuation that got captured
        raw_doi = raw_doi.rstrip('.,;)\'">')

        # Normalize: lowercase, strip URL prefix
        doi_normalized = raw_doi.lower()
        for prefix_pattern in _DOI_URL_PREFIXES:
            doi_normalized = re.sub(prefix_pattern, '', doi_normalized, flags=re.IGNORECASE)

        # Validate: must start with 10. and have a slash
        if re.match(r'^10\.\d{4,9}/.+', doi_normalized):
            return doi_normalized, DoiStatus.FOUND
        else:
            return raw_doi, DoiStatus.MALFORMED

    # No DOI found — check if there's a malformed attempt
    malformed = _MALFORMED_DOI_PATTERN.search(text)
    if malformed and '/' in malformed.group(0):
        return malformed.group(0), DoiStatus.MALFORMED

    # Check for DOI label without value
    if re.search(r'\bdoi\s*:\s*$', text, re.IGNORECASE):
        return None, DoiStatus.MALFORMED

    return None, DoiStatus.MISSING


def normalize_doi(doi: str) -> str:
    """Normalize a DOI to lowercase without URL prefix."""
    doi = doi.strip()
    for prefix_pattern in _DOI_URL_PREFIXES:
        doi = re.sub(prefix_pattern, '', doi, flags=re.IGNORECASE)
    return doi.lower().rstrip('.,;)\'">')


# ---------------------------------------------------------------------------
# Author/year/title extraction (basic heuristics)
# ---------------------------------------------------------------------------

def extract_authors(text: str) -> Optional[List[str]]:
    """Extract author names from reference text (basic heuristic)."""
    # Remove leading number/bracket
    clean = re.sub(r'^\d+[\.\)]\s*|\[\d+\]\s*', '', text.strip())

    # Try semicolon-separated authors first: "Smith, J.; Doe, A.; Jones, E."
    semi_match = re.match(r'^((?:[^;]+;)+[^;.]+?)\.\s+[A-Z"(]', clean)
    if semi_match:
        author_str = semi_match.group(1)
        authors = [a.strip() for a in author_str.split(';') if len(a.strip()) > 2]
        if len(authors) >= 2:
            return authors[:10]

    # Try single author or "Author. Title" pattern
    author_match = re.match(r'^([^.]+?)\.\s+[A-Z"(]', clean)
    if author_match:
        author_str = author_match.group(1)
        authors = re.split(r';\s*|\s+and\s+', author_str)
        authors = [a.strip() for a in authors if len(a.strip()) > 2]
        if authors:
            return authors[:10]

    return None


def extract_year(text: str) -> Optional[int]:
    """Extract publication year from reference text."""
    # Look for 4-digit year between 1900-2030
    matches = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', text)
    if matches:
        return int(matches[0])
    return None


def extract_title(text: str) -> Optional[str]:
    """Extract title from reference text (basic heuristic)."""
    # Remove leading number/bracket and authors
    clean = re.sub(r'^\d+[\.\)]\s*|\[\d+\]\s*', '', text.strip())

    # Title is often in quotes or after a period
    quoted = re.search(r'["""](.+?)["""]', clean)
    if quoted:
        return quoted.group(1).strip()

    # Try: after first period (end of author list)
    parts = clean.split('.')
    if len(parts) >= 2:
        candidate = parts[1].strip()
        if 10 < len(candidate) < 200:
            return candidate

    return None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    document_id: str
    references: List[Reference] = field(default_factory=list)
    total: int = 0
    found_doi: int = 0
    missing_doi: int = 0
    malformed_doi: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_references(document_id: str, db: Session) -> ExtractionResult:
    """
    Full BE-3 pipeline for reference extraction:
    1. Get references section from DB
    2. Split into individual references
    3. Extract DOI, authors, year, title
    4. Store in references table
    5. Update document status
    """
    doc_repo = DocumentRepository(db)
    sec_repo = DocumentSectionRepository(db)
    ref_repo = ReferenceRepository(db)

    doc = doc_repo.get(document_id)
    if not doc:
        return ExtractionResult(
            document_id=document_id,
            error=f"Document '{document_id}' not found.",
        )

    # Update status
    doc.status = DocumentProcessingStatus.REFERENCES_EXTRACTING
    db.commit()
    logger.info(f"[reference_service] {document_id} — starting reference extraction")

    try:
        # ── Step 1: Get references section(s) ──────────────────────────────
        sections = sec_repo.list_by_document(document_id)
        ref_sections = [s for s in sections if s.type == SectionType.references]

        if not ref_sections:
            logger.warning(f"[reference_service] {document_id} — no references section found")
            doc.status = DocumentProcessingStatus.REFERENCES_EXTRACTED
            db.commit()
            return ExtractionResult(
                document_id=document_id,
                error="No references section found in document.",
            )

        # Combine all reference sections, pick the longest one
        # (Acknowledgments may also be classified as references)
        ref_section_text = max(
            (s.full_text or "" for s in ref_sections),
            key=len,
        )
        logger.info(f"[reference_service] {document_id} — references section: {len(ref_section_text)} chars")

        # ── Step 2: Split into individual references ─────────────────────────
        raw_refs = split_references(ref_section_text)
        logger.info(f"[reference_service] {document_id} — split into {len(raw_refs)} references")

        # ── Step 3: Delete old references ────────────────────────────────────
        existing = ref_repo.list_by_document(document_id)
        for r in existing:
            db.delete(r)
        db.flush()

        # ── Step 4: Extract DOI + metadata, store ────────────────────────────
        result = ExtractionResult(document_id=document_id)

        for i, raw_ref in enumerate(raw_refs):
            doi_normalized, doi_status = extract_doi(raw_ref)
            authors = extract_authors(raw_ref)
            year = extract_year(raw_ref)
            title = extract_title(raw_ref)

            ref = Reference(
                reference_id=f"ref_{uuid.uuid4().hex[:8]}",
                document_id=document_id,
                raw_reference=raw_ref,
                extracted_title=title,
                extracted_authors=authors,
                extracted_year=year,
                extracted_doi=doi_normalized,
                doi_normalized=doi_normalized,
                doi_status=doi_status,
                metadata_status=MetadataStatus.NOT_LOOKED_UP,
                position=i + 1,
            )
            db.add(ref)
            result.references.append(ref)

            if doi_status == DoiStatus.FOUND:
                result.found_doi += 1
            elif doi_status == DoiStatus.MISSING:
                result.missing_doi += 1
            elif doi_status == DoiStatus.MALFORMED:
                result.malformed_doi += 1

        result.total = len(raw_refs)

        # ── Step 5: Update document ───────────────────────────────────────────
        doc.references_count = result.total
        doc.status = DocumentProcessingStatus.REFERENCES_EXTRACTED
        db.commit()

        logger.info(
            f"[reference_service] {document_id} — REFERENCES_EXTRACTED: "
            f"{result.total} refs, {result.found_doi} DOIs found, "
            f"{result.missing_doi} missing, {result.malformed_doi} malformed"
        )
        return result

    except Exception as exc:
        doc.status = DocumentProcessingStatus.FAILED
        db.commit()
        logger.error(f"[reference_service] {document_id} — extraction failed: {exc}")
        return ExtractionResult(document_id=document_id, error=str(exc))
