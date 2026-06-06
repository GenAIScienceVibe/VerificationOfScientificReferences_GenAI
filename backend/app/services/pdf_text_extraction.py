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
                text = page.get_text("text") or ""
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
