from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Claim, ClaimReferenceLink, Document, EvidencePackage, Reference, SourceMetadata
from app.models.enums import DocumentStatus, EvidenceAvailability, MappingStatus
from app.repositories import DocumentRepository, EvidencePackageRepository
from app.services.doi_metadata_lookup import _authors_to_list, metadata_to_dict

logger = logging.getLogger(__name__)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


class EvidencePackageBuilder:
    """BE-7 evidence package coordinator.

    BE-7 packages backend-owned data into a stable contract for later RAG/ML
    integration. It never calls RAG/ML, GenAI verification, publisher scraping,
    or external metadata services.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def prepare_evidence_for_document(self, document_id: str, db: Session, *, request_id: str | None = None) -> dict[str, Any]:
        document = DocumentRepository(db).get(document_id)
        if not document:
            raise AppException(
                status_code=404,
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                field="document_id",
                detail=f"Document '{document_id}' was not found.",
                message="Document not found",
            )
        first_claim = db.scalar(select(Claim).where(Claim.document_id == document_id).limit(1))
        if first_claim is None:
            raise AppException(
                status_code=409,
                code=ErrorCode.CLAIM_NOT_FOUND,
                field="document_id",
                detail="No claims exist for this document. Run BE-6 claim extraction before preparing evidence.",
                message="Claims not found",
            )

        links = self._load_links(document_id, db)
        if not links:
            raise AppException(
                status_code=409,
                code=ErrorCode.CLAIM_REFERENCE_LINK_NOT_FOUND,
                field="document_id",
                detail="No claim-reference links exist for this document. Run BE-6 claim extraction/mapping first.",
                message="Claim-reference links not found",
            )

        logger.info("evidence_preparation_start", extra={"document_id": document_id, "request_id": request_id, "links_count": len(links)})
        document.status = DocumentStatus.EVIDENCE_PREPARING.value
        db.commit()

        repo = EvidencePackageRepository(db)
        repo.delete_for_document(document_id)

        created: list[EvidencePackage] = []
        skipped: list[dict[str, Any]] = []
        for link in links:
            package = self._build_package_for_link(document, link, db)
            if package is None:
                skipped.append({"link_id": link.id, "mapping_status": link.mapping_status, "reason": "No reference_id available for evidence package"})
                continue
            db.add(package)
            created.append(package)
        db.flush()

        availability_counts = Counter(package.evidence_availability for package in created)
        document.status = DocumentStatus.EVIDENCE_READY.value if created else DocumentStatus.PARTIAL_FAILED.value
        db.commit()
        for package in created:
            db.refresh(package)
        db.refresh(document)

        logger.info(
            "evidence_preparation_completed",
            extra={
                "document_id": document_id,
                "request_id": request_id,
                "links_count": len(links),
                "packages_created": len(created),
                "availability_counts": dict(availability_counts),
                "skipped_count": len(skipped),
            },
        )
        return {
            "document_id": document.id,
            "evidence_packages_created": len(created),
            "metadata_only": availability_counts.get(EvidenceAvailability.METADATA_ONLY.value, 0),
            "abstract_available": availability_counts.get(EvidenceAvailability.ABSTRACT_AVAILABLE.value, 0),
            "full_text_available": availability_counts.get(EvidenceAvailability.FULL_TEXT_AVAILABLE.value, 0),
            "source_unavailable": availability_counts.get(EvidenceAvailability.SOURCE_UNAVAILABLE.value, 0),
            "skipped_links_count": len(skipped),
            "skipped_links": skipped[:25],
            "status": document.status,
            "phase": "BE-7",
            "is_stub": False,
            "processing_note": "BE-7 prepared structured evidence packages only. It did not call RAG/ML or GenAI verification.",
        }

    def get_claim_evidence_package(self, claim_id: str, db: Session) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if not claim:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail=f"Claim '{claim_id}' was not found.", message="Claim not found")
        packages = EvidencePackageRepository(db).list_for_claim(claim_id)
        if not packages:
            raise AppException(status_code=404, code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND, field="claim_id", detail="No evidence package has been built for this claim yet. Run /prepare-evidence first.", message="Evidence package not found")
        return {"claim_id": claim.id, "document_id": claim.document_id, "evidence_packages": [self.package_to_contract(package) for package in packages]}

    def list_document_evidence_packages(self, document_id: str, db: Session, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        document = DocumentRepository(db).get(document_id)
        if not document:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail=f"Document '{document_id}' was not found.", message="Document not found")
        packages = EvidencePackageRepository(db).list_for_document(document_id)
        total = len(packages)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        page_items = packages[(page - 1) * page_size : page * page_size]
        return {"document_id": document_id, "total": total, "page": page, "page_size": page_size, "evidence_packages": [self.package_to_contract(package) for package in page_items]}

    def _load_links(self, document_id: str, db: Session) -> list[ClaimReferenceLink]:
        statement = (
            select(ClaimReferenceLink)
            .options(
                selectinload(ClaimReferenceLink.claim),
                selectinload(ClaimReferenceLink.citation),
                selectinload(ClaimReferenceLink.reference).selectinload(Reference.metadata_records),
            )
            .where(ClaimReferenceLink.document_id == document_id)
            .order_by(ClaimReferenceLink.created_at, ClaimReferenceLink.id)
        )
        return list(db.scalars(statement).all())

    def _build_package_for_link(self, document: Document, link: ClaimReferenceLink, db: Session) -> EvidencePackage | None:
        if not link.reference_id or not link.reference:
            return None
        reference = link.reference
        metadata = self._latest_metadata(reference)
        metadata_payload = self._metadata_payload(reference, metadata)
        evidence_availability, evidence_text, source_url = self._source_evidence(metadata_payload, metadata)
        warnings = self._warnings_for_link(link, metadata, evidence_availability)
        return EvidencePackage(
            document_id=document.id,
            claim_id=link.claim_id,
            reference_id=reference.id,
            citation_id=link.citation_id,
            link_id=link.id,
            citation_text=link.citation.raw_citation if link.citation else None,
            doi=reference.extracted_doi or (metadata.doi if metadata else None),
            doi_status=reference.doi_status,
            metadata_json=metadata_payload,
            source_evidence_text=evidence_text,
            source_url=source_url,
            evidence_availability=evidence_availability,
            package_warnings_json=warnings or None,
            embedding_model_version=self.settings.embedding_model_version,
            prompt_version=self.settings.verification_prompt_version,
            verification_policy_version=self.settings.verification_policy_version,
        )

    def _latest_metadata(self, reference: Reference) -> SourceMetadata | None:
        if not reference.metadata_records:
            return None
        return sorted(reference.metadata_records, key=lambda item: (item.updated_at or item.created_at, item.id), reverse=True)[0]

    def _metadata_payload(self, reference: Reference, metadata: SourceMetadata | None) -> dict[str, Any]:
        if metadata is not None:
            payload = metadata_to_dict(metadata) or {}
            payload["source"] = "source_metadata"
            payload["raw_reference"] = reference.raw_reference
            return payload
        return {
            "source": "reference_extracted_fields",
            "doi": reference.extracted_doi,
            "title": reference.extracted_title,
            "authors": _authors_to_list(reference.extracted_authors),
            "year": reference.extracted_year,
            "venue": None,
            "publisher": None,
            "abstract": None,
            "url": None,
            "lookup_source": None,
            "lookup_status": reference.metadata_status,
            "metadata_match_score": reference.metadata_match_score,
            "raw_reference": reference.raw_reference,
        }

    def _source_evidence(self, metadata_payload: dict[str, Any], metadata: SourceMetadata | None) -> tuple[str, str | None, str | None]:
        abstract = (metadata_payload.get("abstract") or "").strip() if isinstance(metadata_payload.get("abstract"), str) else None
        source_url = metadata_payload.get("url") if isinstance(metadata_payload.get("url"), str) else None
        raw = metadata.raw_metadata_json if metadata is not None else None
        full_text = None
        if isinstance(raw, dict):
            maybe_full_text = raw.get("full_text") or raw.get("fullText") or raw.get("source_full_text")
            if isinstance(maybe_full_text, str) and maybe_full_text.strip():
                full_text = maybe_full_text.strip()
        if full_text:
            return EvidenceAvailability.FULL_TEXT_AVAILABLE.value, full_text, source_url
        if abstract:
            return EvidenceAvailability.ABSTRACT_AVAILABLE.value, abstract, source_url
        has_metadata = any(
            _non_empty(metadata_payload.get(key))
            for key in ("title", "authors", "year", "venue", "publisher", "doi", "url")
        )
        if has_metadata:
            return EvidenceAvailability.METADATA_ONLY.value, None, source_url
        return EvidenceAvailability.SOURCE_UNAVAILABLE.value, None, source_url

    def _warnings_for_link(self, link: ClaimReferenceLink, metadata: SourceMetadata | None, evidence_availability: str) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        if link.mapping_status != MappingStatus.MAPPED.value:
            warnings.append({"code": "UNCERTAIN_MAPPING", "detail": f"Mapping status is {link.mapping_status}. Human review may be needed."})
        if metadata is None:
            warnings.append({"code": "METADATA_UNAVAILABLE", "detail": "No BE-5 SourceMetadata record was available; reference-extracted fields were packaged as fallback metadata."})
        if evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value:
            warnings.append({"code": "SOURCE_EVIDENCE_UNAVAILABLE", "detail": "No abstract, full text, or usable metadata source evidence is available."})
        return warnings

    def package_to_contract(self, package: EvidencePackage) -> dict[str, Any]:
        metadata = package.metadata_json or {}
        claim = package.claim
        reference = package.reference
        source_evidence = {
            "evidence_availability": package.evidence_availability,
            "text": package.source_evidence_text,
            "source_url": package.source_url,
        }
        return {
            "evidence_package_id": package.id,
            "document_id": package.document_id,
            "claim_id": package.claim_id,
            "reference_id": package.reference_id,
            "citation_id": package.citation_id,
            "link_id": package.link_id,
            "claim_text": claim.claim_text if claim else None,
            "citation_text": package.citation_text,
            "doi": package.doi,
            "doi_status": package.doi_status,
            "metadata": {
                "title": metadata.get("title"),
                "authors": metadata.get("authors") or [],
                "year": metadata.get("year"),
                "venue": metadata.get("venue"),
                "publisher": metadata.get("publisher"),
                "abstract": metadata.get("abstract"),
                "doi": metadata.get("doi") or package.doi,
                "url": metadata.get("url"),
                "lookup_source": metadata.get("lookup_source"),
                "lookup_status": metadata.get("lookup_status"),
                "metadata_match_score": metadata.get("metadata_match_score"),
                "source": metadata.get("source"),
            },
            "source_evidence": source_evidence,
            "policy": {
                "embedding_model_version": package.embedding_model_version,
                "prompt_version": package.prompt_version,
                "verification_policy_version": package.verification_policy_version,
            },
            "mapping": {
                "mapping_status": package.claim_reference_link.mapping_status if package.claim_reference_link else None,
                "mapping_confidence": package.claim_reference_link.mapping_confidence if package.claim_reference_link else None,
                "mapping_reason": package.claim_reference_link.mapping_reason if package.claim_reference_link else None,
            },
            "reference": {
                "reference_key": reference.reference_key if reference else None,
                "raw_reference": reference.raw_reference if reference else None,
                "extracted_title": reference.extracted_title if reference else None,
                "extracted_authors": reference.extracted_authors if reference else None,
                "extracted_year": reference.extracted_year if reference else None,
            },
            "warnings": package.package_warnings_json or [],
            "created_at": _iso(package.created_at),
            "updated_at": _iso(package.updated_at),
        }
