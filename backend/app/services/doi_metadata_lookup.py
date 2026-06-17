from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.clients.metadata_clients import CrossrefClient, DoiResolverClient, MetadataLookupResponse
from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Document, Reference, SourceMetadata
from app.models.enums import DocumentStatus, DoiStatus, MetadataStatus
from app.repositories import DocumentRepository, ReferenceRepository, SourceMetadataRepository
from app.services.metadata_scoring import calculate_metadata_match
from app.services.reference_extraction import reference_to_dict

logger = logging.getLogger(__name__)

DOI_CANDIDATE_REGEX = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)?(10\.\d{4,9}/\S+)", re.IGNORECASE)


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

# This is a more permissive DOI syntax check used for validating extracted DOIs before lookup.
def _strip_reference_noise(text: str) -> str:
    """
    Clean a raw reference string for use as a CrossRef bibliographic search
    query, when no extracted_title is available.

    Removes:
      - leading reference numbers ("12. ", "[3] ", "45.")
      - "[CrossRef]" / "[Google Scholar]" markers
      - trailing stray reference numbers picked up during splitting
      - excessive whitespace

    This is best-effort text cleanup, not a structured title extractor —
    CrossRef's bibliographic search is fairly tolerant of noisy queries,
    and search_by_title()'s similarity check filters out bad matches.
    """
    import re as _re

    cleaned = text.strip()

    # Strip leading "12. " / "[12] " / "12) " reference numbering
    cleaned = _re.sub(r"^\s*(\[\d+\]|\d{1,3}[\.\)])\s*", "", cleaned)

    # Remove [CrossRef] / [Google Scholar] / [PubMed] style markers
    cleaned = _re.sub(r"\[(CrossRef|Google Scholar|PubMed|PMC)\]", " ", cleaned, flags=_re.IGNORECASE)

    # Truncate at the first long run of digits that looks like a trailing
    # reference number block (e.g. "... 100012. 46." -> stop before "46.")
    cleaned = _re.sub(r"\s+\d{1,3}\.\s*$", "", cleaned)

    # Collapse whitespace
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()

    # CrossRef bibliographic queries work best with a reasonable length —
    # very long strings (multi-reference blobs from imperfect splitting)
    # dilute the match. Cap at ~300 chars.
    if len(cleaned) > 300:
        cleaned = cleaned[:300]

    return cleaned

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
        doi_resolver_client: DoiResolverClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.crossref_client = crossref_client or CrossrefClient(self.settings)
        self.doi_resolver_client = doi_resolver_client or DoiResolverClient(self.settings)

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

    # def _verify_reference(
    #     self,
    #     reference: Reference,
    #     db: Session,
    #     *,
    #     request_id: str | None = None,
    #     force_refresh: bool = False,
    #     raise_for_missing: bool = True,
    # ) -> SourceMetadata | None:
    #     logger.info(
    #         "metadata_lookup_start",
    #         extra={"reference_id": reference.id, "document_id": reference.document_id, "doi": reference.extracted_doi, "request_id": request_id},
    #     )
    #     metadata_repo = SourceMetadataRepository(db)
    #     doi = normalize_doi_for_lookup(reference.extracted_doi)

    #     if not doi:
    #         reference.doi_status = DoiStatus.MISSING.value
    #         reference.metadata_status = MetadataStatus.METADATA_UNAVAILABLE.value
    #         metadata = metadata_repo.upsert_for_reference(
    #             reference_id=reference.id,
    #             doi=None,
    #             title=None,
    #             authors=None,
    #             year=None,
    #             venue=None,
    #             publisher=None,
    #             abstract=None,
    #             url=None,
    #             lookup_source="BE-5",
    #             lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
    #             raw_metadata_json={"reason": "missing_doi"},
    #             title_match=None,
    #             author_match=None,
    #             year_match=None,
    #             doi_match=None,
    #             metadata_match_score=None,
    #             commit=False,
    #         )
    #         db.commit()
    #         if raise_for_missing:
    #             raise AppException(
    #                 status_code=422,
    #                 code=ErrorCode.DOI_MISSING,
    #                 field="reference_id",
    #                 detail="This reference does not contain an extracted DOI.",
    #                 message="DOI missing",
    #             )
    #         return metadata

    #     if not is_valid_doi_syntax(doi):
    #         reference.extracted_doi = doi
    #         reference.doi_status = DoiStatus.MALFORMED.value
    #         reference.metadata_status = MetadataStatus.METADATA_UNAVAILABLE.value
    #         metadata = metadata_repo.upsert_for_reference(
    #             reference_id=reference.id,
    #             doi=doi,
    #             title=None,
    #             authors=None,
    #             year=None,
    #             venue=None,
    #             publisher=None,
    #             abstract=None,
    #             url=None,
    #             lookup_source="BE-5",
    #             lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
    #             raw_metadata_json={"reason": "malformed_doi"},
    #             title_match=None,
    #             author_match=None,
    #             year_match=None,
    #             doi_match=False,
    #             metadata_match_score=None,
    #             commit=False,
    #         )
    #         db.commit()
    #         if raise_for_missing:
    #             raise AppException(
    #                 status_code=422,
    #                 code=ErrorCode.DOI_MALFORMED,
    #                 field="reference_id",
    #                 detail="The extracted DOI is malformed and cannot be looked up safely.",
    #                 message="DOI malformed",
    #             )
    #         return metadata

    #     reference.extracted_doi = doi

    #     existing = metadata_repo.get_latest_for_reference(reference.id)
    #     if existing and existing.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value and not force_refresh:
    #         reference.doi_status = DoiStatus.VALID.value
    #         reference.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED.value
    #         reference.metadata_match_score = existing.metadata_match_score
    #         db.commit()
    #         return existing

    #     cached = metadata_repo.find_success_by_doi(doi) if not force_refresh else None
    #     if cached and cached.reference_id != reference.id:
    #         metadata = self._copy_cached_metadata(reference, cached, db)
    #         reference.doi_status = DoiStatus.VALID.value
    #         reference.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED.value
    #         reference.metadata_match_score = metadata.metadata_match_score
    #         db.commit()
    #         db.refresh(metadata)
    #         return metadata

    #     if not self.settings.metadata_lookup_enabled:
    #         reference.metadata_status = MetadataStatus.LOOKUP_FAILED.value
    #         db.commit()
    #         raise AppException(
    #             status_code=503,
    #             code=ErrorCode.METADATA_SERVICE_UNAVAILABLE,
    #             field="reference_id",
    #             detail="Metadata lookup is disabled by METADATA_LOOKUP_ENABLED=false.",
    #             message="Metadata lookup disabled",
    #         )

    #     response = self.crossref_client.lookup_by_doi(doi)
    #     metadata = self._persist_lookup_response(reference, response, db)
    #     logger.info(
    #         "metadata_lookup_completed",
    #         extra={
    #             "reference_id": reference.id,
    #             "document_id": reference.document_id,
    #             "doi": doi,
    #             "request_id": request_id,
    #             "lookup_source": response.lookup_source,
    #             "lookup_status": response.lookup_status,
    #             "metadata_match_score": reference.metadata_match_score,
    #         },
    #     )
    #     return metadata

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

        if not doi:
            # No DOI was extracted from the reference text. Try a CrossRef
            # title-based search as a best-effort fallback before giving up.
            title_search_result = self._try_title_search(reference, db)
            if title_search_result is not None:
                return title_search_result

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
                raw_metadata_json={"reason": "missing_doi", "title_search_attempted": bool(reference.extracted_title)},
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
                    detail="This reference does not contain an extracted DOI and no "
                           "confident CrossRef title match was found.",
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

    def _try_title_search(self, reference: Reference, db: Session) -> SourceMetadata | None:
        """
        Attempt to find metadata via CrossRef title search when no DOI was
        extracted.

        Many references in this dataset have extracted_title == None (BE-4.2
        only fills extracted_year reliably). As a pragmatic fallback, if
        extracted_title is missing we use raw_reference as the search query —
        CrossRef's bibliographic search tolerates full reference strings
        reasonably well, and the similarity check in search_by_title()
        guards against bad matches.

        Returns the persisted SourceMetadata on a confident match, or None
        if no fallback could be attempted / no confident match was found
        (caller proceeds with the normal MISSING-DOI path).
        """
        if not getattr(self.settings, "metadata_title_search_enabled", True):
            return None
        if not self.settings.metadata_lookup_enabled:
            return None

        query_text = reference.extracted_title or reference.raw_reference
        if not query_text or len(query_text.strip()) < 8:
            return None

        # raw_reference can contain a leading reference number ("12. ") and
        # trailing [CrossRef]/page markers — strip the most obvious noise so
        # the bibliographic query focuses on author/title/journal text.
        cleaned_query = _strip_reference_noise(query_text)
        if not cleaned_query:
            return None

        authors = _authors_to_list(reference.extracted_authors) if reference.extracted_authors else None

        response = self.crossref_client.search_by_title(
            cleaned_query,
            authors=authors,
            year=reference.extracted_year,
        )

        if not response.success:
            return None

        metadata = self._persist_lookup_response(reference, response, db)
        logger.info(
            "metadata_lookup_completed_via_title_search",
            extra={
                "reference_id": reference.id,
                "document_id": reference.document_id,
                "found_doi": response.doi,
                "lookup_source": response.lookup_source,
                "metadata_match_score": reference.metadata_match_score,
                "used_raw_reference_fallback": reference.extracted_title is None,
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
            lookup_source=f"metadata_cache:{cached.lookup_source.removeprefix('metadata_cache:')}",
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
