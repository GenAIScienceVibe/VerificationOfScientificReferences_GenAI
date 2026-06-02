"""
BE-2 Text Extraction Service
----------------------------
Handles:
  - Raw text extraction from PDF (pdfplumber)
  - Raw text cleaning (line breaks, artifacts, encoding)
  - Section detection (GenAI via Claude, fallback to regex)
  - Storing results in document_sections table
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import List, Tuple

from dotenv import load_dotenv
load_dotenv()

import pdfplumber
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentProcessingStatus,
    DocumentSection,
    SectionType,
)
from app.db.repositories import DocumentRepository, DocumentSectionRepository
from app.logger import logger
from app.services.section_detection_service import (
    DetectedSection,
    detect_sections,
)


from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ExtractionResult:
    document_id: str
    raw_text: str
    cleaned_text: str
    sections: List[DetectedSection] = field(default_factory=list)
    page_count: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_raw_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, int]:
    """
    Extract raw text from PDF bytes using pdfplumber.
    Handles single-column and two-column layouts by splitting
    each page at the midpoint and reading left then right column.
    Returns (raw_text, page_count).
    """
    raw_pages = []
    page_count = 0

    with pdfplumber.open(__import__("io").BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            width = page.width
            height = page.height
            mid = width / 2

            # Extract left and right columns separately
            left_text = page.crop((0, 0, mid, height)).extract_text() or ""
            right_text = page.crop((mid, 0, width, height)).extract_text() or ""

            # Decide: if both columns have substantial text → two-column layout
            if len(left_text.strip()) > 100 and len(right_text.strip()) > 100:
                combined = left_text + "\n\n" + right_text
            else:
                # Single-column fallback
                combined = page.extract_text() or ""

            if combined.strip():
                raw_pages.append(combined)

    return "\n\n".join(raw_pages), page_count


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(raw_text: str) -> str:
    """
    Clean raw extracted text:
    - Normalize unicode characters
    - Remove non-printable characters
    - Fix hyphenated line breaks (e.g. "demon-\nstrate" → "demonstrate")
    - Remove unnecessary line breaks within paragraphs
    - Normalize whitespace
    - Preserve paragraph breaks (double newlines)
    """
    # 1. Normalize unicode
    text = unicodedata.normalize("NFKC", raw_text)

    # 2. Remove non-printable characters except newlines and tabs
    text = "".join(c for c in text if c.isprintable() or c in "\n\t")

    # 3. Fix hyphenated line breaks: "demon-\nstrate" → "demonstrate"
    text = re.sub(r"-\n(\w)", r"\1", text)

    # 4. Replace single newlines within a paragraph with a space
    #    (double newlines = paragraph break, keep those)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # 5. Collapse multiple spaces into one
    text = re.sub(r" {2,}", " ", text)

    # 6. Collapse more than 2 consecutive newlines into exactly 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 7. Strip leading/trailing whitespace per paragraph
    paragraphs = [p.strip() for p in text.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]

    return "\n\n".join(paragraphs)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_document_text(
    document_id: str,
    pdf_bytes: bytes,
    db: Session,
) -> ExtractionResult:
    """
    Full BE-2 pipeline for a single document:
      1. Extract raw text from PDF
      2. Clean text
      3. Detect sections
      4. Store in DB
      5. Update document status
    """
    doc_repo = DocumentRepository(db)
    sec_repo = DocumentSectionRepository(db)

    doc = doc_repo.get(document_id)
    if not doc:
        return ExtractionResult(
            document_id=document_id,
            raw_text="",
            cleaned_text="",
            error=f"Document '{document_id}' not found.",
        )

    # ── Update status to extracting ──────────────────────────────────────────
    doc.status = DocumentProcessingStatus.TEXT_EXTRACTING
    db.commit()
    logger.info(f"[text_service] {document_id} — starting text extraction")

    try:
        # ── Step 1: Extract raw text ─────────────────────────────────────────
        raw_text, page_count = extract_raw_text_from_pdf(pdf_bytes)
        logger.info(f"[text_service] {document_id} — extracted {len(raw_text)} chars from {page_count} pages")

        if not raw_text.strip():
            raise ValueError("PDF appears to be empty or image-only (no extractable text).")

        # ── Step 2: Clean text ───────────────────────────────────────────────
        cleaned_text = clean_text(raw_text)
        logger.info(f"[text_service] {document_id} — cleaned text: {len(cleaned_text)} chars")

        # ── Step 3: Detect sections ──────────────────────────────────────────
        # Pass raw_text so section headers can be found before line-joining
        sections = detect_sections(cleaned_text, raw_text=raw_text)
        logger.info(f"[text_service] {document_id} — detected {len(sections)} sections: "
                    f"{[s.type.value for s in sections]}")

        # ── Step 4: Delete old sections and store new ones ───────────────────
        existing = sec_repo.list_by_document(document_id)
        for s in existing:
            db.delete(s)
        db.flush()

        for sec in sections:
            db.add(DocumentSection(
                document_id=document_id,
                section_id=f"sec_{uuid.uuid4().hex[:8]}",
                name=sec.name,
                type=sec.type,
                order_index=sec.order_index,
                text_preview=sec.text_preview,
                full_text=sec.full_text,
                start_char=sec.start_char,
                end_char=sec.end_char,
            ))

        # ── Step 5: Update document metadata ────────────────────────────────
        doc.page_count = page_count
        doc.status = DocumentProcessingStatus.TEXT_EXTRACTED
        db.commit()
        logger.info(f"[text_service] {document_id} — TEXT_EXTRACTED, {len(sections)} sections stored")

        return ExtractionResult(
            document_id=document_id,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            sections=sections,
            page_count=page_count,
        )

    except Exception as exc:
        doc.status = DocumentProcessingStatus.FAILED
        db.commit()
        logger.error(f"[text_service] {document_id} — extraction failed: {exc}")
        return ExtractionResult(
            document_id=document_id,
            raw_text="",
            cleaned_text="",
            error=str(exc),
        )


def process_text_document(
    document_id: str,
    text: str,
    db: Session,
) -> ExtractionResult:
    """
    BE-2 pipeline for plain-text uploads (no PDF extraction needed).
    Cleans text, detects sections, stores in DB.
    """
    doc_repo = DocumentRepository(db)
    sec_repo = DocumentSectionRepository(db)

    doc = doc_repo.get(document_id)
    if not doc:
        return ExtractionResult(
            document_id=document_id,
            raw_text="",
            cleaned_text="",
            error=f"Document '{document_id}' not found.",
        )

    doc.status = DocumentProcessingStatus.TEXT_EXTRACTING
    db.commit()
    logger.info(f"[text_service] {document_id} — processing plain text ({len(text)} chars)")

    try:
        cleaned_text = clean_text(text)
        sections = detect_sections(cleaned_text, raw_text=text)
        logger.info(f"[text_service] {document_id} — detected {len(sections)} sections")

        existing = sec_repo.list_by_document(document_id)
        for s in existing:
            db.delete(s)
        db.flush()

        for sec in sections:
            db.add(DocumentSection(
                document_id=document_id,
                section_id=f"sec_{uuid.uuid4().hex[:8]}",
                name=sec.name,
                type=sec.type,
                order_index=sec.order_index,
                text_preview=sec.text_preview,
                full_text=sec.full_text,
                start_char=sec.start_char,
                end_char=sec.end_char,
            ))

        doc.status = DocumentProcessingStatus.TEXT_EXTRACTED
        db.commit()
        logger.info(f"[text_service] {document_id} — TEXT_EXTRACTED")

        return ExtractionResult(
            document_id=document_id,
            raw_text=text,
            cleaned_text=cleaned_text,
            sections=sections,
            page_count=0,
        )

    except Exception as exc:
        doc.status = DocumentProcessingStatus.FAILED
        db.commit()
        logger.error(f"[text_service] {document_id} — text processing failed: {exc}")
        return ExtractionResult(
            document_id=document_id,
            raw_text="",
            cleaned_text="",
            error=str(exc),
        )
