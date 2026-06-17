from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppException, ErrorCode
from app.models import (
    Claim,
    ClaimReferenceLink,
    Document,
    EvidencePackage,
    Reference,
    SourceMetadata,
)
from app.models.enums import (
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
)
from app.repositories import DocumentRepository

logger = logging.getLogger(__name__)

# Versioning fields stored on every evidence package. These are intentionally
# static placeholders for BE-7 — later phases (BE-8/BE-9) may make these
# configurable per pipeline run.
EMBEDDING_MODEL_VERSION = "text-embedding-3-small-v1"
PROMPT_VERSION = "claim-verification-prompt-v1"
VERIFICATION_POLICY_VERSION = "policy-v1"


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


def _reference_title(reference: Reference | None) -> str | None:
    if reference is None:
        return None
    if reference.extracted_title:
        return reference.extracted_title
    return (reference.raw_reference[:160] + "...") if len(reference.raw_reference) > 160 else reference.raw_reference


def _build_metadata_json(reference: Reference, metadata: SourceMetadata | None) -> dict[str, Any] | None:
    """Build the structured metadata snapshot stored on the evidence package."""
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
    }


def _determine_evidence_level(reference: Reference, metadata: SourceMetadata | None) -> tuple[str, str | None]:
    """
    Determine the evidence availability level and the source evidence text
    (if any) for a claim-reference pair.

    Levels, from best to worst:
      - FULL_TEXT_AVAILABLE: never promised in BE-7 (no full-text retrieval
        exists yet); reserved for a future phase.
      - ABSTRACT_AVAILABLE: metadata lookup succeeded and an abstract is present.
      - METADATA_ONLY: metadata lookup succeeded but no abstract is available.
      - SOURCE_UNAVAILABLE: no DOI, malformed DOI, or metadata lookup did not
        succeed — nothing usable beyond the reference text itself.
    """
    if metadata is not None and metadata.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value:
        if metadata.abstract and metadata.abstract.strip():
            return EvidenceAvailability.ABSTRACT_AVAILABLE.value, metadata.abstract.strip()
        return EvidenceAvailability.METADATA_ONLY.value, None

    return EvidenceAvailability.SOURCE_UNAVAILABLE.value, None


class EvidencePackageService:
    """BE-7 evidence package builder.

    Builds one evidence package per claim-reference pair (MAPPED links only).
    Evidence packages intentionally avoid promising full-text availability —
    only metadata/abstract content already stored from BE-5 is included.

    This service does not call RAG/ML or GenAI. Sending the package to a
    RAG/ML service is a no-op placeholder until BE-9 wires the real client.
    """

    def prepare_evidence_for_document(
        self,
        document_id: str,
        db: Session,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        document = DocumentRepository(db).get(document_id)
        if not document:
            raise AppException(
                status_code=404,
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                field="document_id",
                detail=f"Document '{document_id}' was not found.",
                message="Document not found",
            )

        links = list(
            db.scalars(
                select(ClaimReferenceLink)
                .options(
                    selectinload(ClaimReferenceLink.claim),
                    selectinload(ClaimReferenceLink.citation),
                    selectinload(ClaimReferenceLink.reference).selectinload(Reference.metadata_records),
                )
                .where(
                    ClaimReferenceLink.document_id == document_id,
                    ClaimReferenceLink.mapping_status == MappingStatus.MAPPED.value,
                    ClaimReferenceLink.reference_id.is_not(None),
                )
            ).all()
        )

        if not links:
            raise AppException(
                status_code=409,
                code=ErrorCode.CLAIMS_NOT_FOUND if hasattr(ErrorCode, "CLAIMS_NOT_FOUND") else ErrorCode.REFERENCES_NOT_FOUND,
                field="document_id",
                detail="No mapped claim-reference links were found. Run /extract-claims first.",
                message="No mapped claims found",
            )

        logger.info(
            "evidence_preparation_start",
            extra={"document_id": document_id, "request_id": request_id, "mapped_links_count": len(links)},
        )

        document.status = DocumentStatus.EVIDENCE_PREPARING.value
        db.commit()

        # Replace any existing evidence packages for this document so this
        # endpoint can be safely re-run after re-extraction.
        db.execute(delete(EvidencePackage).where(EvidencePackage.document_id == document_id))
        db.flush()

        evidence_counts: dict[str, int] = {level.value: 0 for level in EvidenceAvailability}
        stored_packages: list[EvidencePackage] = []

        # One evidence package per (claim, reference) pair. A claim can map to
        # multiple references via multiple links/citations; dedupe on that pair.
        seen_pairs: set[tuple[str, str]] = set()

        for link in links:
            claim = link.claim
            reference = link.reference
            if claim is None or reference is None:
                continue

            pair_key = (claim.id, reference.id)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            metadata = max(
                reference.metadata_records,
                key=lambda item: item.updated_at or item.created_at,
                default=None,
            ) if reference.metadata_records else None

            evidence_level, source_text = _determine_evidence_level(reference, metadata)
            metadata_json = _build_metadata_json(reference, metadata)
            source_url = metadata.url if metadata else None

            package = EvidencePackage(
                document_id=document_id,
                claim_id=claim.id,
                reference_id=reference.id,
                citation_text=link.citation.raw_citation if link.citation else None,
                doi=reference.extracted_doi,
                doi_status=reference.doi_status or DoiStatus.MISSING.value,
                metadata_json=metadata_json,
                source_evidence_text=source_text,
                source_url=source_url,
                evidence_availability=evidence_level,
                embedding_model_version=EMBEDDING_MODEL_VERSION,
                prompt_version=PROMPT_VERSION,
                verification_policy_version=VERIFICATION_POLICY_VERSION,
            )
            db.add(package)
            stored_packages.append(package)
            evidence_counts[evidence_level] += 1

        db.flush()

        # Send to RAG/ML service — placeholder no-op for BE-7. The real
        # integration (POST /internal/rag/...) is wired in BE-9.
        rag_dispatch_count = self._send_to_rag_service(stored_packages)

        document.status = DocumentStatus.EVIDENCE_READY.value
        db.commit()
        for package in stored_packages:
            db.refresh(package)
        db.refresh(document)

        logger.info(
            "evidence_preparation_completed",
            extra={
                "document_id": document_id,
                "request_id": request_id,
                "evidence_packages_count": len(stored_packages),
                "evidence_level_counts": evidence_counts,
                "rag_dispatch_count": rag_dispatch_count,
            },
        )

        return {
            "document_id": document.id,
            "evidence_packages_count": len(stored_packages),
            "evidence_level_counts": evidence_counts,
            "rag_dispatch_count": rag_dispatch_count,
            "status": document.status,
            "phase": "BE-7",
            "is_stub": False,
            "processing_note": (
                "BE-7 evidence packages built from existing claim-reference links and BE-5 "
                "metadata. Full-text evidence is not available; evidence levels reflect only "
                "metadata/abstract availability. RAG/ML dispatch is a placeholder until BE-9."
            ),
        }

    def _send_to_rag_service(self, packages: list[EvidencePackage]) -> int:
        """
        Placeholder for sending evidence packages to the RAG/ML service.

        BE-7 scope only requires that evidence packages are built and stored;
        the actual RAG/ML client integration (with timeout/fallback handling)
        is implemented in BE-9. This method exists so the orchestration call
        site is already in place and easy to wire up later.
        """
        return len(packages)

    def get_evidence_package_for_claim(self, claim_id: str, db: Session) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if not claim:
            raise AppException(
                status_code=404,
                code=ErrorCode.CLAIM_NOT_FOUND,
                field="claim_id",
                detail=f"Claim '{claim_id}' was not found.",
                message="Claim not found",
            )

        package = db.scalar(
            select(EvidencePackage)
            .options(
                selectinload(EvidencePackage.reference),
                selectinload(EvidencePackage.claim),
            )
            .where(EvidencePackage.claim_id == claim_id)
            .order_by(EvidencePackage.created_at.desc())
        )
        if not package:
            raise AppException(
                status_code=404,
                code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND
                if hasattr(ErrorCode, "EVIDENCE_PACKAGE_NOT_FOUND")
                else ErrorCode.CLAIM_REFERENCE_LINK_NOT_FOUND,
                field="claim_id",
                detail=f"No evidence package has been prepared for claim '{claim_id}'. Run /prepare-evidence first.",
                message="Evidence package not found",
            )

        return self._package_to_dict(package)

    def _package_to_dict(self, package: EvidencePackage) -> dict[str, Any]:
        reference = package.reference
        claim = package.claim
        return {
            "evidence_package_id": package.id,
            "document_id": package.document_id,
            "claim_id": package.claim_id,
            "reference_id": package.reference_id,
            "claim_text": claim.claim_text if claim else None,
            "citation_text": package.citation_text,
            "doi": package.doi,
            "doi_status": package.doi_status,
            "metadata": package.metadata_json,
            "abstract": (package.metadata_json or {}).get("abstract") if package.metadata_json else None,
            "source_evidence_text": package.source_evidence_text,
            "source_url": package.source_url,
            "evidence_availability": package.evidence_availability,
            "reference_title": _reference_title(reference) if reference else None,
            "policy": {
                "embedding_model_version": package.embedding_model_version,
                "prompt_version": package.prompt_version,
                "verification_policy_version": package.verification_policy_version,
            },
            "created_at": _iso(package.created_at),
            "updated_at": _iso(package.updated_at),
            "phase": "BE-7",
            "is_stub": False,
            "processing_note": (
                "Evidence package for RAG/ML and verification. evidence_availability reflects "
                "what is actually stored — full document text is not promised."
            ),
        }
