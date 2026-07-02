from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppException, ErrorCode


@dataclass(frozen=True)
class PdfExtractionResult:
    raw_text: str
    pages_count: int
    page_texts: list[dict[str, object]]
    warnings: list[str]


def _extract_page_text(page: object) -> str:  # type: ignore[type-arg]
    """Extract text from a single PDF page with two-column layout detection.

    Uses block-level extraction so we can sort blocks by visual reading order.
    For two-column layouts (median block width < 55 % of page width) we read
    the left column top-to-bottom, then the right column top-to-bottom.
    Single-column pages are sorted by y-position only.
    """
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
    # block_type 0 = text, 1 = image — keep only text blocks with content
    text_blocks = [b for b in blocks if len(b) > 6 and b[6] == 0 and b[4].strip()]

    if not text_blocks:
        return ""

    page_width: float = page.rect.width
    if page_width <= 0:
        return "\n".join(b[4].rstrip("\n") for b in sorted(text_blocks, key=lambda b: b[1]))

    # Two-column heuristic: if the median block width is narrower than 55 % of
    # the page, the page most likely has two columns.  We require at least 4
    # blocks to avoid misclassifying sparse pages (e.g. chapter title pages).
    widths = sorted(b[2] - b[0] for b in text_blocks)
    median_width = widths[len(widths) // 2]
    is_two_column = len(text_blocks) >= 4 and median_width < page_width * 0.55

    if is_two_column:
        # Use the horizontal centre of each block to assign it to a column.
        mid = page_width / 2
        left_col = sorted(
            [(b[1], b[4].rstrip("\n")) for b in text_blocks if (b[0] + b[2]) / 2 < mid],
            key=lambda t: t[0],
        )
        right_col = sorted(
            [(b[1], b[4].rstrip("\n")) for b in text_blocks if (b[0] + b[2]) / 2 >= mid],
            key=lambda t: t[0],
        )
        return "\n".join(text for _, text in left_col + right_col)

    # Single column: sort all blocks top-to-bottom.
    return "\n".join(b[4].rstrip("\n") for b in sorted(text_blocks, key=lambda b: b[1]))


class PdfTextExtractionService:
    """Text-based PDF extraction for BE-3.

    OCR is intentionally out of scope. Image-only/scanned PDFs are reported as
    extraction failures instead of sending content to external services.
    """

    def extract(self, pdf_path: Path) -> PdfExtractionResult:
        try:
            import fitz  # PyMuPDF
        except Exception as exc:  # pragma: no cover - dependency is installed in validation env
            raise AppException(
                status_code=500,
                code=ErrorCode.TEXT_EXTRACTION_FAILED,
                field="file",
                detail="PyMuPDF is not installed. Install requirements.txt before running PDF extraction.",
                message="PDF text extraction dependency missing",
            ) from exc

        try:
            document = fitz.open(str(pdf_path))
        except Exception as exc:
            raise AppException(
                status_code=422,
                code=ErrorCode.PDF_READ_FAILED,
                field="file",
                detail="The uploaded PDF could not be opened or read.",
                message="PDF read failed",
            ) from exc

        try:
            page_texts: list[dict[str, object]] = []
            warnings: list[str] = []
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                text = _extract_page_text(page)
                if not text.strip():
                    warnings.append(f"Page {page_index + 1} did not contain extractable text.")
                page_texts.append({"page_number": page_index + 1, "text": text})
            raw_text = "\n\n".join(str(item["text"]) for item in page_texts).strip()
        finally:
            document.close()

        if not raw_text:
            raise AppException(
                status_code=422,
                code=ErrorCode.TEXT_EXTRACTION_FAILED,
                field="file",
                detail="No readable text could be extracted. The PDF may be scanned or image-only. OCR is out of scope for BE-3.",
                message="PDF text extraction failed",
            )

        return PdfExtractionResult(raw_text=raw_text, pages_count=len(page_texts), page_texts=page_texts, warnings=warnings)
