from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

import httpx
from sqlalchemy.orm import Session

import pymupdf

from app.clients.metadata_clients import CoreClient, CrossrefClient, DoiResolverClient, GoogleBooksClient, MetadataLookupResponse, OpenAlexClient, OpenReviewClient, PubMedClient, SemanticScholarClient, SsrnClient, UnpaywallClient
from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Document, Reference, SourceMetadata
from app.models.enums import DocumentStatus, DoiStatus, MetadataStatus
from app.repositories import DocumentRepository, ReferenceRepository, SourceMetadataRepository
from app.services.metadata_scoring import calculate_metadata_match
from app.services.reference_extraction import reference_to_dict

logger = logging.getLogger(__name__)

DOI_CANDIDATE_REGEX = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)?(10\.\d{4,9}/\S+)", re.IGNORECASE)
_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
# Matches openreview.net forum, pdf, and abstract URL variants; captures the submission ID.
_OPENREVIEW_URL_RE = re.compile(
    r"openreview\.net/(?:forum|pdf|abstract)\?id=([\w-]+)",
    re.IGNORECASE,
)

# Matches the title after a year anchor in common reference formats:
#   APA:              Smith, J. (2023). Title. Journal.
#   SMJ / Harvard:    Smith J. 2023. Title. Journal.
#   Broken fragment:  2003. Title. Journal.   (author split off by 2-column PDF)
# Accepts year with or without parentheses; stops before venue (period + uppercase/digit),
# doi:, URL, or end of string.
_RAW_REF_TITLE_RE = re.compile(
    r"(?:\(\d{4}[a-z]?\)|\b\d{4})\.\s+(.+?)(?=\.\s+[A-Z\d]|\s+doi\s*[: ]|\s+https?://|$)",
    re.IGNORECASE,
)


def _extract_title_from_raw_reference(raw_reference: str) -> str | None:
    """Extract a paper title from a raw reference string when extracted_title is unavailable.

    Covers APA (Author (Year). Title. Venue.) and numbered formats ([1] / 1.).
    Returns None when no reliable title can be found (too short or no year anchor).
    """
    if not raw_reference:
        return None
    m = _RAW_REF_TITLE_RE.search(raw_reference)
    if m:
        title = m.group(1).strip().rstrip(".")
        if len(title) >= 10:
            return title
    return None


# Matches ISBN-13 (978/979 prefix) and ISBN-10, with optional separators.
_ISBN_RE = re.compile(
    r"\b(?:97[89][-\s]?(?:\d[-\s]?){9}\d|(?:\d[-\s]?){9}[\dXx])\b"
)


def _extract_openreview_id(raw_reference: str) -> str | None:
    """Extract an OpenReview submission ID from a raw reference string.

    Handles all three URL variants used by the OpenReview platform:
        https://openreview.net/forum?id=XYZ
        https://openreview.net/pdf?id=XYZ
        https://openreview.net/abstract?id=XYZ
    Returns None when no OpenReview URL is found.
    """
    m = _OPENREVIEW_URL_RE.search(raw_reference)
    return m.group(1) if m else None


def _extract_isbn(raw_reference: str) -> str | None:
    """Extract the first ISBN-10 or ISBN-13 found in a raw reference string.

    Many textbook citations in APA bibliographies include an ISBN explicitly
    (e.g. 'ISBN 978-1-4625-2175-4'). Extracting it lets us query CrossRef by
    ISBN when no DOI is present — the most reliable path for books.

    Returns the ISBN with hyphens/spaces stripped, or None if none is found.
    """
    m = _ISBN_RE.search(raw_reference)
    return re.sub(r"[-\s]", "", m.group(0)) if m else None


def _arxiv_pdf_url(doi: str) -> str | None:
    """Return a direct arxiv.org PDF URL if doi is an arXiv DOI, else None."""
    m = _ARXIV_DOI_RE.match(doi.strip())
    return f"https://arxiv.org/pdf/{m.group(1)}" if m else None


def normalize_doi_for_lookup(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().strip("<>")
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)", "", doi, flags=re.IGNORECASE).strip()
    doi = doi.rstrip(",;")
    doi = doi.rstrip(".")
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]
    doi = doi.strip().lower()
    if not doi:
        return None
    return doi


def is_valid_doi_syntax(doi: str | None) -> bool:
    if not doi:
        return False
    return bool(re.fullmatch(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", doi.strip().lower()))


def metadata_to_dict(metadata: SourceMetadata | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {
        "metadata_id": metadata.id,
        "doi": metadata.doi,
        "title": metadata.title,
        "authors": _authors_to_list(metadata.authors),
        "year": metadata.year,
        "venue": metadata.venue,
        "publisher": metadata.publisher,
        "abstract": metadata.abstract,
        "url": metadata.url,
        "lookup_source": metadata.lookup_source,
        "lookup_status": metadata.lookup_status,
        "metadata_match_score": metadata.metadata_match_score,
        "match_details": {
            "title_match": metadata.title_match,
            "author_match": metadata.author_match,
            "year_match": metadata.year_match,
            "doi_match": metadata.doi_match,
        },
        "created_at": _iso(metadata.created_at),
        "updated_at": _iso(metadata.updated_at),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _authors_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _authors_to_storage(value: list[str] | None) -> str | None:
    if not value:
        return None
    return "; ".join(item.strip() for item in value if item and item.strip()) or None


def _extract_fulltext_from_bytes(pdf_bytes: bytes, *, max_chars: int) -> str | None:
    """Extract plain text from raw PDF bytes using PyMuPDF.

    Used when the PDF is uploaded directly by the user rather than downloaded.
    Returns None if the bytes are not a valid PDF or contain no extractable text.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages_text = [page.get_text() for page in doc]
        doc.close()
    except Exception:
        return None
    text = "\n".join(pages_text).strip()
    if not text:
        return None
    return text[:max_chars] if len(text) > max_chars else text


def _extract_fulltext_from_url(pdf_url: str, *, max_bytes: int, max_chars: int) -> str | None:
    """Download a PDF from *pdf_url* and extract plain text with PyMuPDF.

    Returns None on any failure (timeout, non-PDF, image-only, empty text)
    so callers can fall back gracefully without crashing the lookup pipeline.
    """
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            with client.stream("GET", pdf_url) as r:
                if r.status_code != 200:
                    return None
                content_type = r.headers.get("content-type", "")
                if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
                    return None
                chunks: list[bytes] = []
                total = 0
                for chunk in r.iter_bytes(chunk_size=65_536):
                    total += len(chunk)
                    if total > max_bytes:
                        return None
                    chunks.append(chunk)
        pdf_bytes = b"".join(chunks)
    except Exception:
        return None

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages_text = [page.get_text() for page in doc]
        doc.close()
    except Exception:
        return None

    text = "\n".join(pages_text).strip()
    if not text:
        return None
    return text[:max_chars] if len(text) > max_chars else text


def _merge_fulltext(primary: MetadataLookupResponse, full_text: str, pdf_url: str) -> MetadataLookupResponse:
    """Return a new response identical to *primary* but with *full_text* injected
    into raw_metadata_json so EvidencePackageBuilder promotes the package to
    FULL_TEXT_AVAILABLE."""
    raw = dict(primary.raw_metadata_json) if isinstance(primary.raw_metadata_json, dict) else {}
    raw["full_text"] = full_text
    raw["full_text_source"] = pdf_url
    return MetadataLookupResponse(
        success=primary.success,
        lookup_source=primary.lookup_source,
        lookup_status=primary.lookup_status,
        doi=primary.doi,
        title=primary.title,
        authors=primary.authors,
        year=primary.year,
        venue=primary.venue,
        publisher=primary.publisher,
        abstract=primary.abstract,
        url=pdf_url,
        raw_metadata_json=raw,
        status_code=primary.status_code,
    )


def _merge_abstract_fallback(primary: MetadataLookupResponse, fallback: MetadataLookupResponse) -> MetadataLookupResponse:
    """Return a new response that keeps all CrossRef fields but fills in the
    abstract (and open-access URL when the primary has none) from the fallback.
    The lookup_source is updated to reflect both providers."""
    combined_source = f"{primary.lookup_source}+{fallback.lookup_source}"
    return MetadataLookupResponse(
        success=primary.success,
        lookup_source=combined_source,
        lookup_status=primary.lookup_status,
        doi=primary.doi,
        title=primary.title,
        authors=primary.authors,
        year=primary.year,
        venue=primary.venue,
        publisher=primary.publisher,
        abstract=fallback.abstract,
        url=primary.url or fallback.url,
        raw_metadata_json=primary.raw_metadata_json,
        status_code=primary.status_code,
    )


class MetadataLookupService:
    """BE-5 DOI metadata lookup coordinator.

    This service only sends normalized DOI values to backend-controlled metadata
    clients. It never sends uploaded PDF/text content to CrossRef/OpenAlex/RAG/GenAI.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        crossref_client: CrossrefClient | None = None,
        openalex_client: OpenAlexClient | None = None,
        semantic_scholar_client: SemanticScholarClient | None = None,
        unpaywall_client: UnpaywallClient | None = None,
        core_client: CoreClient | None = None,
        ssrn_client: SsrnClient | None = None,
        pubmed_client: PubMedClient | None = None,
        google_books_client: GoogleBooksClient | None = None,
        doi_resolver_client: DoiResolverClient | None = None,
        openreview_client: OpenReviewClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.crossref_client = crossref_client or CrossrefClient(self.settings)
        self.openalex_client = openalex_client or OpenAlexClient(self.settings)
        self.semantic_scholar_client = semantic_scholar_client or SemanticScholarClient(self.settings)
        self.unpaywall_client = unpaywall_client or UnpaywallClient(self.settings)
        self.core_client = core_client or CoreClient(self.settings)
        self.ssrn_client = ssrn_client or SsrnClient(self.settings)
        self.pubmed_client = pubmed_client or PubMedClient(self.settings)
        self.google_books_client = google_books_client or GoogleBooksClient(self.settings)
        self.doi_resolver_client = doi_resolver_client or DoiResolverClient(self.settings)
        self.openreview_client = openreview_client or OpenReviewClient(self.settings)

    def verify_reference_doi(self, reference_id: str, db: Session, *, request_id: str | None = None, force_refresh: bool = False) -> dict[str, Any]:
        reference = ReferenceRepository(db).get(reference_id)
        if not reference:
            raise AppException(
                status_code=404,
                code=ErrorCode.REFERENCE_NOT_FOUND,
                field="reference_id",
                detail=f"Reference '{reference_id}' was not found.",
                message="Reference not found",
            )
        metadata = self._verify_reference(reference, db, request_id=request_id, force_refresh=force_refresh)
        return self._reference_metadata_response(reference, metadata)

    def verify_document_dois(self, document_id: str, db: Session, *, request_id: str | None = None, force_refresh: bool = False) -> dict[str, Any]:
        document = DocumentRepository(db).get(document_id)
        if not document:
            raise AppException(
                status_code=404,
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                field="document_id",
                detail=f"Document '{document_id}' was not found.",
                message="Document not found",
            )
        references = ReferenceRepository(db).list_for_document(document_id)
        document.status = DocumentStatus.DOI_VERIFYING.value
        db.commit()

        processed: list[Reference] = []
        errors: list[dict[str, str]] = []
        for reference in references:
            try:
                self._verify_reference(reference, db, request_id=request_id, force_refresh=force_refresh, raise_for_missing=False)
            except AppException as exc:
                errors.append({"reference_id": reference.id, "code": exc.error.code, "detail": exc.error.detail})
            processed.append(reference)

        db.flush()
        counts = Counter(reference.doi_status for reference in processed)
        metadata_counts = Counter(reference.metadata_status for reference in processed)
        usable = bool(processed) and any(
            reference.metadata_status == MetadataStatus.LOOKUP_SUCCEEDED.value for reference in processed
        )
        if usable or not errors:
            document.status = DocumentStatus.DOI_VERIFIED.value
        else:
            document.status = DocumentStatus.PARTIAL_FAILED.value
        db.commit()
        db.refresh(document)
        for reference in processed:
            db.refresh(reference)

        logger.info(
            "document_doi_verification_completed",
            extra={
                "document_id": document_id,
                "request_id": request_id,
                "total_references": len(processed),
                "doi_counts": dict(counts),
                "metadata_counts": dict(metadata_counts),
            },
        )

        return {
            "document_id": document.id,
            "total_references": len(processed),
            "valid_dois": counts.get(DoiStatus.VALID.value, 0),
            "missing_dois": counts.get(DoiStatus.MISSING.value, 0),
            "invalid_dois": counts.get(DoiStatus.INVALID.value, 0),
            "malformed_dois": counts.get(DoiStatus.MALFORMED.value, 0),
            "lookup_failed": metadata_counts.get(MetadataStatus.LOOKUP_FAILED.value, 0),
            "metadata_succeeded": metadata_counts.get(MetadataStatus.LOOKUP_SUCCEEDED.value, 0),
            "metadata_unavailable": metadata_counts.get(MetadataStatus.METADATA_UNAVAILABLE.value, 0),
            "status": document.status,
            "errors": errors,
            "phase": "BE-5",
            "is_stub": False,
            "processing_note": "BE-5 DOI metadata lookup completed. This verifies metadata availability only, not claim support.",
        }

    def get_reference_metadata(self, reference_id: str, db: Session) -> dict[str, Any]:
        reference = ReferenceRepository(db).get(reference_id)
        if not reference:
            raise AppException(
                status_code=404,
                code=ErrorCode.REFERENCE_NOT_FOUND,
                field="reference_id",
                detail=f"Reference '{reference_id}' was not found.",
                message="Reference not found",
            )
        metadata = SourceMetadataRepository(db).get_latest_for_reference(reference_id)
        if metadata is None:
            raise AppException(
                status_code=404,
                code=ErrorCode.METADATA_UNAVAILABLE,
                field="reference_id",
                detail="No metadata has been stored for this reference yet. Run /verify-doi first.",
                message="Metadata unavailable",
            )
        return self._reference_metadata_response(reference, metadata)

    def _verify_reference(
        self,
        reference: Reference,
        db: Session,
        *,
        request_id: str | None = None,
        force_refresh: bool = False,
        raise_for_missing: bool = True,
    ) -> SourceMetadata | None:
        logger.info(
            "metadata_lookup_start",
            extra={"reference_id": reference.id, "document_id": reference.document_id, "doi": reference.extracted_doi, "request_id": request_id},
        )
        metadata_repo = SourceMetadataRepository(db)
        doi = normalize_doi_for_lookup(reference.extracted_doi)

        # The disabled-mode guard must apply before title-based DOI resolution.
        # The local missing/malformed handling below remains available so mock
        # and offline pipelines persist safe statuses without provider calls.
        if not doi and self.settings.metadata_lookup_enabled:
            # OpenReview lookup — NeurIPS, ICLR, ICML, and other ML-venue papers are
            # often cited with only an openreview.net URL and no DOI. Calling the API
            # yields the paper title (and occasionally a registered DOI), which is then
            # fed into the title chain below. This runs first so the title chain has
            # the best possible search string.
            openreview_id = _extract_openreview_id(reference.raw_reference or "")
            if openreview_id:
                or_response = self.openreview_client.lookup_by_id(openreview_id)
                if or_response.success:
                    if or_response.doi:
                        resolved_doi = normalize_doi_for_lookup(or_response.doi)
                        if resolved_doi:
                            doi = resolved_doi
                            reference.extracted_doi = doi
                            logger.info(
                                "doi_resolved_via_openreview",
                                extra={"reference_id": reference.id, "openreview_id": openreview_id, "found_doi": doi},
                            )
                    if not doi and or_response.title and not reference.extracted_title:
                        # No registered DOI from OpenReview; inject title so the
                        # title chain has a reliable search string.
                        reference.extracted_title = or_response.title
                        if not reference.extracted_authors and or_response.authors:
                            reference.extracted_authors = "; ".join(or_response.authors)
                        if not reference.extracted_year and or_response.year:
                            reference.extracted_year = or_response.year
                        logger.info(
                            "openreview_title_injected",
                            extra={"reference_id": reference.id, "openreview_id": openreview_id, "title": or_response.title},
                        )
                else:
                    logger.info(
                        "openreview_lookup_failed",
                        extra={"reference_id": reference.id, "openreview_id": openreview_id, "error_code": or_response.error_code},
                    )

            # Title-based DOI lookup: try CrossRef → OpenAlex → SemanticScholar in
            # Order of rate-limit generosity: CrossRef and OpenAlex (unlimited with
            # polite-pool mailto), PubMed (< 3 req/sec, very generous), then
            # SemanticScholar (restricted to ~5-10 unauthenticated req/min), then
            # CORE (10 req/sec with API key). All use the same false-match gates
            # (title substring + year ±1 + first-author last name) and stop at the
            # first confident match. PubMed is placed 3rd for strong coverage of
            # psychology, medicine, and social-science journals.
            # Prefer the structured extracted_title; fall back to parsing raw_reference
            # when the reference parser could not isolate the title (non-standard format).
            search_title = (reference.extracted_title or "").strip() or _extract_title_from_raw_reference(reference.raw_reference)
            if search_title and not doi:
                _title_searchers = [
                    ("CrossRef-TitleSearch", lambda: self.crossref_client.search_by_title(
                        title=search_title,
                        authors=reference.extracted_authors,
                        year=reference.extracted_year,
                    )),
                    ("OpenAlex-TitleSearch", lambda: self.openalex_client.search_by_title(
                        title=search_title,
                        authors=reference.extracted_authors,
                        year=reference.extracted_year,
                    )),
                    ("PubMed-TitleSearch", lambda: self.pubmed_client.search_by_title(
                        title=search_title,
                        authors=reference.extracted_authors,
                        year=reference.extracted_year,
                    )),
                    ("SemanticScholar-TitleSearch", lambda: self.semantic_scholar_client.search_by_title(
                        title=search_title,
                        authors=reference.extracted_authors,
                        year=reference.extracted_year,
                    )),
                ]
                # CORE is added only when an API key is configured — the API requires auth.
                if self.settings.core_api_key:
                    _title_searchers.append(("CORE-TitleSearch", lambda: self.core_client.search_by_title(
                        title=search_title,
                        authors=reference.extracted_authors,
                        year=reference.extracted_year,
                    )))
                for source_name, searcher in _title_searchers:
                    title_response = searcher()
                    if title_response.success and title_response.doi:
                        resolved_doi = normalize_doi_for_lookup(title_response.doi)
                        if resolved_doi:
                            logger.info(
                                "doi_resolved_via_title_search",
                                extra={
                                    "reference_id": reference.id,
                                    "found_doi": resolved_doi,
                                    "lookup_source": source_name,
                                },
                            )
                            doi = resolved_doi
                            reference.extracted_doi = doi
                            break
                    else:
                        logger.info(
                            "title_search_no_confident_match",
                            extra={
                                "reference_id": reference.id,
                                "lookup_source": source_name,
                                "error_code": title_response.error_code,
                            },
                        )

        # ISBN fallback — for textbooks that lack DOIs but include an ISBN in
        # the reference string (e.g. "ISBN 978-1-4625-2175-4"). CrossRef indexes
        # most major publishers by ISBN and can return the registered DOI.
        if not doi and self.settings.metadata_lookup_enabled:
            isbn = _extract_isbn(reference.raw_reference or "")
            if isbn:
                isbn_response = self.crossref_client.lookup_by_isbn(isbn)
                if isbn_response.success and isbn_response.doi:
                    resolved_doi = normalize_doi_for_lookup(isbn_response.doi)
                    if resolved_doi:
                        doi = resolved_doi
                        reference.extracted_doi = doi
                        logger.info(
                            "doi_resolved_via_isbn",
                            extra={"reference_id": reference.id, "isbn": isbn, "found_doi": doi},
                        )

        # Google Books fallback — for textbooks where no DOI exists and no ISBN
        # is written in the reference string. Google Books has near-complete book
        # coverage and returns ISBN-13; we pipe that to CrossRef to find the DOI.
        if not doi and self.settings.metadata_lookup_enabled and search_title:
            gb_isbn = self.google_books_client.find_isbn_by_title(
                search_title,
                authors=reference.extracted_authors,
                year=reference.extracted_year,
            )
            if gb_isbn:
                gb_response = self.crossref_client.lookup_by_isbn(gb_isbn)
                if gb_response.success and gb_response.doi:
                    resolved_doi = normalize_doi_for_lookup(gb_response.doi)
                    if resolved_doi:
                        doi = resolved_doi
                        reference.extracted_doi = doi
                        logger.info(
                            "doi_resolved_via_google_books",
                            extra={"reference_id": reference.id, "isbn": gb_isbn, "found_doi": doi},
                        )

        # raw_reference broader search — last resort when extracted_title was
        # too short or truncated to match. CrossRef's query.bibliographic
        # endpoint accepts full APA strings (author, year, title, venue) so
        # sending the first 200 chars of the raw reference can surface matches
        # that a truncated title query would miss.
        if not doi and self.settings.metadata_lookup_enabled:
            raw_query = (reference.raw_reference or "")[:200].strip()
            if raw_query and raw_query != search_title:
                raw_response = self.crossref_client.search_by_title(
                    title=raw_query,
                    authors=reference.extracted_authors,
                    year=reference.extracted_year,
                )
                if raw_response.success and raw_response.doi:
                    resolved_doi = normalize_doi_for_lookup(raw_response.doi)
                    if resolved_doi:
                        doi = resolved_doi
                        reference.extracted_doi = doi
                        logger.info(
                            "doi_resolved_via_raw_reference",
                            extra={"reference_id": reference.id, "found_doi": doi},
                        )

        if not doi:
            reference.doi_status = DoiStatus.MISSING.value
            reference.metadata_status = MetadataStatus.METADATA_UNAVAILABLE.value
            metadata = metadata_repo.upsert_for_reference(
                reference_id=reference.id,
                doi=None,
                title=None,
                authors=None,
                year=None,
                venue=None,
                publisher=None,
                abstract=None,
                url=None,
                lookup_source="BE-5",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                raw_metadata_json={"reason": "missing_doi"},
                title_match=None,
                author_match=None,
                year_match=None,
                doi_match=None,
                metadata_match_score=None,
                commit=False,
            )
            db.commit()
            if raise_for_missing:
                raise AppException(
                    status_code=422,
                    code=ErrorCode.DOI_MISSING,
                    field="reference_id",
                    detail="This reference does not contain an extracted DOI.",
                    message="DOI missing",
                )
            return metadata

        if not is_valid_doi_syntax(doi):
            reference.extracted_doi = doi
            reference.doi_status = DoiStatus.MALFORMED.value
            reference.metadata_status = MetadataStatus.METADATA_UNAVAILABLE.value
            metadata = metadata_repo.upsert_for_reference(
                reference_id=reference.id,
                doi=doi,
                title=None,
                authors=None,
                year=None,
                venue=None,
                publisher=None,
                abstract=None,
                url=None,
                lookup_source="BE-5",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                raw_metadata_json={"reason": "malformed_doi"},
                title_match=None,
                author_match=None,
                year_match=None,
                doi_match=False,
                metadata_match_score=None,
                commit=False,
            )
            db.commit()
            if raise_for_missing:
                raise AppException(
                    status_code=422,
                    code=ErrorCode.DOI_MALFORMED,
                    field="reference_id",
                    detail="The extracted DOI is malformed and cannot be looked up safely.",
                    message="DOI malformed",
                )
            return metadata

        reference.extracted_doi = doi

        existing = metadata_repo.get_latest_for_reference(reference.id)
        if existing and existing.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value and not force_refresh:
            reference.doi_status = DoiStatus.VALID.value
            reference.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED.value
            reference.metadata_match_score = existing.metadata_match_score
            db.commit()
            return existing

        cached = metadata_repo.find_success_by_doi(doi) if not force_refresh else None
        if cached and cached.reference_id != reference.id:
            metadata = self._copy_cached_metadata(reference, cached, db)
            reference.doi_status = DoiStatus.VALID.value
            reference.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED.value
            reference.metadata_match_score = metadata.metadata_match_score
            db.commit()
            db.refresh(metadata)
            return metadata

        if not self.settings.metadata_lookup_enabled:
            reference.metadata_status = MetadataStatus.LOOKUP_FAILED.value
            db.commit()
            raise AppException(
                status_code=503,
                code=ErrorCode.METADATA_SERVICE_UNAVAILABLE,
                field="reference_id",
                detail="Metadata lookup is disabled by METADATA_LOOKUP_ENABLED=false.",
                message="Metadata lookup disabled",
            )

        response = self.crossref_client.lookup_by_doi(doi)

        # arXiv fallback — CrossRef often doesn't index arXiv preprints.
        # If CrossRef fails and the DOI is an arXiv DOI, try SemanticScholar
        # with the native arXiv ID. If that also fails, build a minimal
        # synthetic success so the PDF extraction step can still run.
        arxiv_pdf = _arxiv_pdf_url(doi)
        if not response.success and arxiv_pdf:
            arxiv_id = _ARXIV_DOI_RE.match(doi).group(1)
            ss_arxiv = self.semantic_scholar_client.lookup_by_arxiv_id(arxiv_id)
            if ss_arxiv.success:
                response = ss_arxiv
                logger.info("arxiv_metadata_semantic_scholar", extra={"reference_id": reference.id, "doi": doi})
            else:
                response = MetadataLookupResponse(
                    success=True,
                    lookup_source="arXiv",
                    lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                    doi=doi,
                    url=arxiv_pdf,
                    raw_metadata_json={"arxiv_id": arxiv_id},
                )
                logger.info("arxiv_synthetic_response", extra={"reference_id": reference.id, "doi": doi})

        # Abstract fallback — CrossRef rarely includes abstracts.
        # Try OpenAlex first, then Semantic Scholar, stopping as soon as one
        # returns an abstract. CrossRef remains the authoritative source for
        # all other fields; only the abstract (and open-access URL when absent)
        # are merged in from the fallback.
        if response.success and not response.abstract:
            openalex = self.openalex_client.lookup_by_doi(doi)
            if openalex.abstract:
                response = _merge_abstract_fallback(response, openalex)
                logger.info("abstract_fallback_openalex", extra={"reference_id": reference.id, "doi": doi})

        if response.success and not response.abstract:
            ss = self.semantic_scholar_client.lookup_by_doi(doi)
            if ss.abstract:
                response = _merge_abstract_fallback(response, ss)
                logger.info("abstract_fallback_semantic_scholar", extra={"reference_id": reference.id, "doi": doi})

        # SSRN abstract enhancement — CrossRef indexes SSRN working papers by DOI
        # (10.2139/ssrn.*) but rarely includes the abstract. When no abstract was
        # found by any prior source, fetch it directly from the SSRN paper page.
        if response.success and not response.abstract:
            ssrn_abstract = self.ssrn_client.get_abstract_for_doi(doi)
            if ssrn_abstract:
                response = _merge_abstract_fallback(
                    response,
                    MetadataLookupResponse(
                        success=True,
                        lookup_source="SSRN",
                        lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                        doi=doi,
                        abstract=ssrn_abstract,
                    ),
                )
                logger.info("abstract_fallback_ssrn", extra={"reference_id": reference.id, "doi": doi})

        # PubMed abstract fallback — strongest coverage for psychology, medicine,
        # neuroscience, and life sciences. CrossRef and OpenAlex often lack abstracts
        # for journals in these domains; PubMed is authoritative for them.
        if response.success and not response.abstract:
            pm = self.pubmed_client.lookup_by_doi(doi)
            if pm.abstract:
                response = _merge_abstract_fallback(response, pm)
                logger.info("abstract_fallback_pubmed", extra={"reference_id": reference.id, "doi": doi})

        # Full-text upgrade — priority: arXiv direct URL → OA URL from metadata
        # → Unpaywall → CORE (inline full text or download URL).
        if response.success:
            pdf_url = arxiv_pdf or (response.url if (response.url and response.url.lower().endswith(".pdf")) else None)
            if not pdf_url and self.settings.unpaywall_email:
                pdf_url = self.unpaywall_client.lookup_by_doi(doi)
                if pdf_url:
                    logger.info("fulltext_pdf_url_unpaywall", extra={"reference_id": reference.id, "doi": doi})
            full_text: str | None = None
            if pdf_url:
                full_text = _extract_fulltext_from_url(
                    pdf_url,
                    max_bytes=self.settings.fulltext_max_bytes,
                    max_chars=self.settings.fulltext_max_chars,
                )
                if full_text:
                    response = _merge_fulltext(response, full_text, pdf_url)
                    logger.info("fulltext_extracted", extra={"reference_id": reference.id, "doi": doi, "chars": len(full_text)})
            # CORE fallback: covers institutional repositories and preprints missed by
            # Unpaywall. CORE returns full text inline when available, eliminating the
            # PDF download step. If only a download URL is returned, we fall back to the
            # standard PDF extraction path.
            if not full_text and self.settings.core_api_key:
                core_text, core_source = self.core_client.get_fulltext_by_doi(doi)
                if core_text:
                    response = _merge_fulltext(response, core_text, core_source or f"core:{doi}")
                    logger.info("fulltext_core_direct", extra={"reference_id": reference.id, "doi": doi, "chars": len(core_text)})
                elif core_source:
                    # CORE found a download URL but no inline full text — try PDF extraction
                    core_pdf_text = _extract_fulltext_from_url(
                        core_source,
                        max_bytes=self.settings.fulltext_max_bytes,
                        max_chars=self.settings.fulltext_max_chars,
                    )
                    if core_pdf_text:
                        response = _merge_fulltext(response, core_pdf_text, core_source)
                        logger.info("fulltext_core_pdf", extra={"reference_id": reference.id, "doi": doi, "chars": len(core_pdf_text)})

        metadata = self._persist_lookup_response(reference, response, db)
        logger.info(
            "metadata_lookup_completed",
            extra={
                "reference_id": reference.id,
                "document_id": reference.document_id,
                "doi": doi,
                "request_id": request_id,
                "lookup_source": response.lookup_source,
                "lookup_status": response.lookup_status,
                "metadata_match_score": reference.metadata_match_score,
            },
        )
        return metadata

    def _copy_cached_metadata(self, reference: Reference, cached: SourceMetadata, db: Session) -> SourceMetadata:
        metadata_authors = _authors_to_list(cached.authors)
        match = calculate_metadata_match(
            extracted_title=reference.extracted_title,
            extracted_authors=reference.extracted_authors,
            extracted_year=reference.extracted_year,
            extracted_doi=reference.extracted_doi,
            metadata_title=cached.title,
            metadata_authors=metadata_authors,
            metadata_year=cached.year,
            metadata_doi=cached.doi,
        )
        return SourceMetadataRepository(db).upsert_for_reference(
            reference_id=reference.id,
            doi=cached.doi,
            title=cached.title,
            authors=cached.authors,
            year=cached.year,
            venue=cached.venue,
            publisher=cached.publisher,
            abstract=cached.abstract,
            url=cached.url,
            lookup_source=f"metadata_cache:{cached.lookup_source}",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            raw_metadata_json=cached.raw_metadata_json,
            title_match=match.title_match,
            author_match=match.author_match,
            year_match=match.year_match,
            doi_match=match.doi_match,
            metadata_match_score=match.metadata_match_score,
            commit=False,
        )

    def _persist_lookup_response(self, reference: Reference, response: MetadataLookupResponse, db: Session) -> SourceMetadata:
        if response.success:
            metadata_doi = normalize_doi_for_lookup(response.doi) or reference.extracted_doi
            url = response.url or (self.doi_resolver_client.resolver_url(metadata_doi) if metadata_doi else None)
            match = calculate_metadata_match(
                extracted_title=reference.extracted_title,
                extracted_authors=reference.extracted_authors,
                extracted_year=reference.extracted_year,
                extracted_doi=reference.extracted_doi,
                metadata_title=response.title,
                metadata_authors=response.authors,
                metadata_year=response.year,
                metadata_doi=metadata_doi,
            )
            metadata = SourceMetadataRepository(db).upsert_for_reference(
                reference_id=reference.id,
                doi=metadata_doi,
                title=response.title,
                authors=_authors_to_storage(response.authors),
                year=response.year,
                venue=response.venue,
                publisher=response.publisher,
                abstract=response.abstract,
                url=url,
                lookup_source=response.lookup_source,
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                raw_metadata_json=response.raw_metadata_json,
                title_match=match.title_match,
                author_match=match.author_match,
                year_match=match.year_match,
                doi_match=match.doi_match,
                metadata_match_score=match.metadata_match_score,
                commit=False,
            )
            reference.doi_status = DoiStatus.VALID.value
            reference.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED.value
            reference.metadata_match_score = match.metadata_match_score
            db.commit()
            db.refresh(metadata)
            return metadata

        status = response.lookup_status
        if response.error_code == "METADATA_UNAVAILABLE" or status == MetadataStatus.METADATA_UNAVAILABLE.value:
            reference.doi_status = DoiStatus.INVALID.value
            reference.metadata_status = MetadataStatus.METADATA_UNAVAILABLE.value
        else:
            reference.doi_status = DoiStatus.FOUND.value
            reference.metadata_status = MetadataStatus.LOOKUP_FAILED.value
        reference.metadata_match_score = None
        metadata = SourceMetadataRepository(db).upsert_for_reference(
            reference_id=reference.id,
            doi=normalize_doi_for_lookup(response.doi) or reference.extracted_doi,
            title=None,
            authors=None,
            year=None,
            venue=None,
            publisher=None,
            abstract=None,
            url=self.doi_resolver_client.resolver_url(reference.extracted_doi) if reference.extracted_doi else None,
            lookup_source=response.lookup_source,
            lookup_status=reference.metadata_status,
            raw_metadata_json={
                "error_code": response.error_code,
                "error_message": response.error_message,
                "status_code": response.status_code,
            },
            title_match=None,
            author_match=None,
            year_match=None,
            doi_match=None,
            metadata_match_score=None,
            commit=False,
        )
        db.commit()
        db.refresh(metadata)
        return metadata

    def inject_fulltext_from_uploaded_pdf(
        self,
        reference_id: str,
        pdf_bytes: bytes,
        filename: str,
        db: Session,
    ) -> dict[str, Any]:
        """Inject full text from a user-uploaded PDF into the SourceMetadata for a reference.

        Used when a paper is paywalled and cannot be fetched automatically via Unpaywall.
        The uploaded PDF is extracted with PyMuPDF and stored in raw_metadata_json["full_text"].
        Running prepare-evidence afterwards will promote the package to FULL_TEXT_AVAILABLE.
        """
        reference = ReferenceRepository(db).get(reference_id)
        if not reference:
            raise AppException(
                status_code=404,
                code=ErrorCode.REFERENCE_NOT_FOUND,
                field="reference_id",
                detail=f"Reference '{reference_id}' was not found.",
                message="Reference not found",
            )

        text = _extract_fulltext_from_bytes(pdf_bytes, max_chars=self.settings.fulltext_max_chars)
        if not text:
            raise AppException(
                status_code=422,
                code=ErrorCode.FILE_REQUIRED,
                field="file",
                detail="The uploaded file could not be read as a PDF or contains no extractable text.",
                message="PDF extraction failed",
            )

        metadata_repo = SourceMetadataRepository(db)
        existing = metadata_repo.get_latest_for_reference(reference_id)

        raw: dict[str, Any] = dict(existing.raw_metadata_json) if isinstance(getattr(existing, "raw_metadata_json", None), dict) else {}
        raw["full_text"] = text
        raw["full_text_source"] = f"user_upload:{filename}"

        metadata_repo.upsert_for_reference(
            reference_id=reference_id,
            doi=existing.doi if existing else normalize_doi_for_lookup(reference.extracted_doi),
            title=existing.title if existing else None,
            authors=existing.authors if existing else None,
            year=existing.year if existing else None,
            venue=existing.venue if existing else None,
            publisher=existing.publisher if existing else None,
            abstract=existing.abstract if existing else None,
            url=existing.url if existing else None,
            lookup_source=(existing.lookup_source if existing else "user_upload"),
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            raw_metadata_json=raw,
            title_match=existing.title_match if existing else None,
            author_match=existing.author_match if existing else None,
            year_match=existing.year_match if existing else None,
            doi_match=existing.doi_match if existing else None,
            metadata_match_score=existing.metadata_match_score if existing else None,
            commit=True,
        )

        logger.info(
            "fulltext_injected_from_upload",
            extra={"reference_id": reference_id, "upload_filename": filename, "chars": len(text)},
        )

        # Collect the claims that cite this reference so the user knows
        # which verification results will improve after prepare-evidence.
        affected_claims = [
            {
                "claim_id": link.claim_id,
                "claim_text": link.claim.claim_text if link.claim else None,
                "citation_raw": link.citation.raw_citation if link.citation else None,
            }
            for link in (reference.claim_links or [])
            if link.claim_id
        ]

        return {
            "reference_id": reference_id,
            "doi": reference.extracted_doi,
            "reference_title": reference.extracted_title,
            "reference_authors": reference.extracted_authors,
            "reference_year": reference.extracted_year,
            "filename": filename,
            "chars_extracted": len(text),
            "full_text_preview": text[:300],
            "affected_claims_count": len(affected_claims),
            "affected_claims": affected_claims,
            "next_step": f"Run POST /documents/{reference.document_id}/prepare-evidence to rebuild evidence packages.",
        }

    def _reference_metadata_response(self, reference: Reference, metadata: SourceMetadata | None) -> dict[str, Any]:
        metadata_dict = metadata_to_dict(metadata)
        match_details = metadata_dict.get("match_details") if metadata_dict else None
        return {
            "reference_id": reference.id,
            "document_id": reference.document_id,
            "doi": reference.extracted_doi,
            "doi_status": reference.doi_status,
            "metadata_status": reference.metadata_status,
            "metadata": metadata_dict,
            "metadata_match_score": reference.metadata_match_score,
            "match_details": match_details,
            "reference": reference_to_dict(reference),
            "phase": "BE-5",
            "is_stub": False,
            "processing_note": "Official DOI metadata lookup result. This does not verify claim support.",
        }
