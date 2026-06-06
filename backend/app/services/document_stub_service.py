"""Backward-compatible import layer from BE-1/BE-2.

The active BE-3 implementation lives in `document_processing_service.py`.
This module is kept only so older imports do not break during incremental
backend phase development.
"""

from app.services.document_processing_service import (  # noqa: F401
    create_text_document,
    create_uploaded_pdf_document,
    document_to_dict,
    get_document,
    get_document_raw_text,
    get_document_sections,
    get_document_status,
)
