from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Citation, Claim, ClaimReferenceLink, Document, DocumentSection, PromptRun, Reference
from app.models.enums import ClaimType, DocumentStatus, MappingStatus
from app.repositories import DocumentRepository, ReferenceRepository
from app.services.citation_mapping import CitationReferenceMapper
from app.services.claim_preparation import ClaimPreparationService
from app.services.genai_claim_extraction import LocalDeterministicClaimExtractionClient

logger = logging.getLogger(__name__)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _reference_title(reference: Reference | None) -> str | None:
    if reference is None:
        return None
    if reference.extracted_title:
        return reference.extracted_title
    return (reference.raw_reference[:160] + "...") if len(reference.raw_reference) > 160 else reference.raw_reference


class ClaimManagementService:
    """BE-6 claim/citation orchestration.

    The default client is deterministic and mockable. It follows the same JSON contract
    expected from the future Groq-backed internal GenAI service, but no live GenAI call
    is required for tests or local validation.
    """

    def __init__(self, claim_client: LocalDeterministicClaimExtractionClient | None = None) -> None:
        self.claim_client = claim_client or LocalDeterministicClaimExtractionClient(get_settings())
        self.preparer = ClaimPreparationService()
        self.mapper = CitationReferenceMapper()

    def extract_claims_for_document(
        self,
        document_id: str,
        db: Session,
        *,
        mode: str = "citation_linked_only",
        sections: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        document = DocumentRepository(db).get(document_id)
        if not document:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail=f"Document '{document_id}' was not found.", message="Document not found")
        if not (document.cleaned_text or document.raw_text):
            raise AppException(status_code=400, code=ErrorCode.DOCUMENT_TEXT_NOT_FOUND, field="document_id", detail="The document does not have processed text for claim extraction.", message="Document text not found")
        references = ReferenceRepository(db).list_for_document(document_id)
        if not references:
            raise AppException(status_code=409, code=ErrorCode.REFERENCES_NOT_FOUND, field="document_id", detail="Extract references before extracting citation-linked claims.", message="References not found")

        logger.info("claim_extraction_start", extra={"document_id": document_id, "request_id": request_id})
        document.status = DocumentStatus.CLAIMS_EXTRACTING.value
        db.commit()

        self._replace_existing_claim_data(document_id, db)
        doc_sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id)).all())
        if sections:
            allowed = {item.lower() for item in sections}
            doc_sections = [section for section in doc_sections if (section.name or "").lower() in allowed]
        prepared_sentences = self.preparer.prepare(document, doc_sections)

        prompt_failures = 0
        stored_claims = 0
        stored_citations = 0
        stored_links = 0
        mapping_counts: Counter[str] = Counter()
        seen_claim_keys: set[tuple[str, str, int | None]] = set()

        for prepared in prepared_sentences:
            try:
                extracted_claims, raw_output = self.claim_client.extract_claims(document_id=document_id, prepared_sentence=prepared)
                prompt_run = PromptRun(
                    document_id=document.id,
                    prompt_type="CLAIM_EXTRACTION",
                    model_provider=self.claim_client.model_provider,
                    model_name=self.claim_client.model_name,
                    prompt_version=self.claim_client.prompt_version,
                    input_summary=f"{prepared.section_name} paragraph={prepared.paragraph_index} sentence={prepared.sentence_index} citations={len(prepared.detected_citations)}",
                    output_json=raw_output,
                    success=True,
                )
                db.add(prompt_run)
            except AppException as exc:
                prompt_failures += 1
                db.add(
                    PromptRun(
                        document_id=document.id,
                        prompt_type="CLAIM_EXTRACTION",
                        model_provider=self.claim_client.model_provider,
                        model_name=self.claim_client.model_name,
                        prompt_version=self.claim_client.prompt_version,
                        input_summary=f"{prepared.section_name} paragraph={prepared.paragraph_index} sentence={prepared.sentence_index}",
                        output_json=None,
                        success=False,
                        error_message=exc.error.detail,
                    )
                )
                continue

            grouped: dict[tuple[str, int | None], list] = {}
            for extracted in extracted_claims:
                grouped.setdefault((extracted.claim_text.lower(), prepared.paragraph_index), []).append(extracted)

            for (_claim_text_key, _paragraph_index), candidates in grouped.items():
                primary = candidates[0]
                key = (primary.claim_text.lower(), "|".join(sorted({item.citation_text for item in candidates})), prepared.paragraph_index)
                if key in seen_claim_keys:
                    continue
                seen_claim_keys.add(key)
                claim = Claim(
                    document_id=document.id,
                    claim_text=primary.claim_text,
                    claim_type=primary.claim_type if primary.claim_type in {item.value for item in ClaimType} else ClaimType.UNKNOWN.value,
                    section_name=prepared.section_name,
                    source_paragraph=prepared.source_paragraph,
                    paragraph_index=prepared.paragraph_index,
                    sentence_index=prepared.sentence_index,
                    extraction_confidence=max(item.confidence for item in candidates),
                )
                db.add(claim)
                db.flush()
                stored_claims += 1

                for extracted in candidates:
                    citation_style = next((item.citation_style for item in prepared.detected_citations if item.citation_text == extracted.citation_text), "UNKNOWN")
                    citation = Citation(
                        document_id=document.id,
                        claim_id=claim.id,
                        raw_citation=extracted.citation_text,
                        citation_style=citation_style,
                        sentence_text=prepared.sentence_text,
                        paragraph_index=prepared.paragraph_index,
                    )
                    db.add(citation)
                    db.flush()
                    stored_citations += 1

                    mappings = self.mapper.map_citation(extracted.citation_text, references)
                    for mapping in mappings:
                        link = ClaimReferenceLink(
                            document_id=document.id,
                            claim_id=claim.id,
                            citation_id=citation.id,
                            reference_id=mapping.reference_id,
                            mapping_status=mapping.mapping_status,
                            mapping_confidence=mapping.mapping_confidence,
                            mapping_reason=mapping.mapping_reason,
                        )
                        db.add(link)
                        stored_links += 1
                        mapping_counts[mapping.mapping_status] += 1
                        if mapping.mapping_status == MappingStatus.MAPPED.value and mapping.reference_id and citation.mapped_reference_id is None:
                            citation.mapped_reference_id = mapping.reference_id
                            citation.mapping_confidence = mapping.mapping_confidence

        document.claims_count = stored_claims
        document.status = DocumentStatus.CLAIMS_EXTRACTED.value if prompt_failures == 0 else DocumentStatus.PARTIAL_FAILED.value
        db.commit()
        logger.info(
            "claim_extraction_completed",
            extra={
                "document_id": document_id,
                "request_id": request_id,
                "candidate_sentences": len(prepared_sentences),
                "claims_count": stored_claims,
                "citations_count": stored_citations,
                "links_count": stored_links,
                "mapping_counts": dict(mapping_counts),
                "prompt_failures": prompt_failures,
            },
        )
        return {
            "document_id": document.id,
            "candidate_citation_sentences": len(prepared_sentences),
            "claims_count": stored_claims,
            "citations_count": stored_citations,
            "mapped_links_count": mapping_counts.get(MappingStatus.MAPPED.value, 0),
            "uncertain_links_count": mapping_counts.get(MappingStatus.UNCERTAIN.value, 0) + mapping_counts.get(MappingStatus.MULTIPLE_MATCHES.value, 0) + mapping_counts.get(MappingStatus.NEEDS_HUMAN_REVIEW.value, 0),
            "no_match_links_count": mapping_counts.get(MappingStatus.NO_MATCH.value, 0),
            "status": document.status,
            "phase": "BE-6",
            "is_stub": False,
            "processing_note": "BE-6 extracted citation-linked claims and mapped citations to existing references. It did not verify support.",
            "warnings": [f"{prompt_failures} prompt chunks failed validation"] if prompt_failures else [],
        }

    def _replace_existing_claim_data(self, document_id: str, db: Session) -> None:
        claim_ids = list(db.scalars(select(Claim.id).where(Claim.document_id == document_id)).all())
        citation_ids = list(db.scalars(select(Citation.id).where(Citation.document_id == document_id)).all())
        if claim_ids:
            db.execute(delete(ClaimReferenceLink).where(ClaimReferenceLink.claim_id.in_(claim_ids)))
        elif citation_ids:
            db.execute(delete(ClaimReferenceLink).where(ClaimReferenceLink.citation_id.in_(citation_ids)))
        db.execute(delete(Citation).where(Citation.document_id == document_id))
        db.execute(delete(Claim).where(Claim.document_id == document_id))
        db.execute(delete(PromptRun).where(PromptRun.document_id == document_id, PromptRun.prompt_type == "CLAIM_EXTRACTION"))
        db.flush()

    def list_claims(self, document_id: str, db: Session, *, claim_type: str | None = None, mapping_status: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self._ensure_document(document_id, db)
        query = select(Claim).options(selectinload(Claim.citations), selectinload(Claim.reference_links)).where(Claim.document_id == document_id)
        if claim_type:
            query = query.where(Claim.claim_type == claim_type)
        claims = list(db.scalars(query.order_by(Claim.created_at, Claim.id)).all())
        if mapping_status:
            claims = [claim for claim in claims if any(link.mapping_status == mapping_status for link in claim.reference_links)]
        total = len(claims)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        claims_page = claims[(page - 1) * page_size : page * page_size]
        return {"document_id": document_id, "total": total, "page": page, "page_size": page_size, "claims": [self._claim_summary(claim) for claim in claims_page]}

    def get_claim(self, claim_id: str, db: Session) -> dict[str, Any]:
        claim = db.scalar(select(Claim).options(selectinload(Claim.citations), selectinload(Claim.reference_links)).where(Claim.id == claim_id))
        if not claim:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail=f"Claim '{claim_id}' was not found.", message="Claim not found")
        return self._claim_summary(claim, include_source=True)

    def list_citations(self, document_id: str, db: Session, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self._ensure_document(document_id, db)
        total = int(db.scalar(select(func.count()).select_from(Citation).where(Citation.document_id == document_id)) or 0)
        citations = list(db.scalars(select(Citation).where(Citation.document_id == document_id).order_by(Citation.created_at, Citation.id).offset((page - 1) * page_size).limit(page_size)).all())
        return {"document_id": document_id, "total": total, "page": page, "page_size": page_size, "citations": [self._citation_dict(item) for item in citations]}

    def list_claim_reference_links(self, document_id: str, db: Session, *, mapping_status: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self._ensure_document(document_id, db)
        query = select(ClaimReferenceLink).options(selectinload(ClaimReferenceLink.claim), selectinload(ClaimReferenceLink.citation), selectinload(ClaimReferenceLink.reference)).where(ClaimReferenceLink.document_id == document_id)
        if mapping_status:
            query = query.where(ClaimReferenceLink.mapping_status == mapping_status)
        links = list(db.scalars(query.order_by(ClaimReferenceLink.created_at, ClaimReferenceLink.id)).all())
        total = len(links)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        page_links = links[(page - 1) * page_size : page * page_size]
        return {"document_id": document_id, "total": total, "page": page, "page_size": page_size, "links": [self._link_dict(link) for link in page_links]}

    def get_claim_reference_link(self, link_id: str, db: Session) -> dict[str, Any]:
        link = db.scalar(select(ClaimReferenceLink).options(selectinload(ClaimReferenceLink.claim), selectinload(ClaimReferenceLink.citation), selectinload(ClaimReferenceLink.reference)).where(ClaimReferenceLink.id == link_id))
        if not link:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_REFERENCE_LINK_NOT_FOUND, field="link_id", detail=f"Claim-reference link '{link_id}' was not found.", message="Claim-reference link not found")
        return self._link_dict(link, include_details=True)

    def _ensure_document(self, document_id: str, db: Session) -> Document:
        document = db.get(Document, document_id)
        if not document:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail=f"Document '{document_id}' was not found.", message="Document not found")
        return document

    def _claim_summary(self, claim: Claim, *, include_source: bool = False) -> dict[str, Any]:
        first_citation = claim.citations[0] if claim.citations else None
        statuses = [link.mapping_status for link in claim.reference_links]
        mapping_status = MappingStatus.MAPPED.value if MappingStatus.MAPPED.value in statuses else (statuses[0] if statuses else None)
        data = {
            "claim_id": claim.id,
            "document_id": claim.document_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "section_name": claim.section_name,
            "citation_text": first_citation.raw_citation if first_citation else None,
            "page_number": claim.page_number,
            "paragraph_index": claim.paragraph_index,
            "sentence_index": claim.sentence_index,
            "extraction_confidence": claim.extraction_confidence,
            "mapping_status": mapping_status,
            "created_at": _iso(claim.created_at),
            "updated_at": _iso(claim.updated_at),
        }
        if include_source:
            data["source_paragraph"] = claim.source_paragraph
            data["citations"] = [self._citation_dict(citation) for citation in claim.citations]
            data["claim_reference_links"] = [self._link_dict(link) for link in claim.reference_links]
        else:
            data["source_paragraph"] = claim.source_paragraph
        return data

    def _citation_dict(self, citation: Citation) -> dict[str, Any]:
        return {
            "citation_id": citation.id,
            "document_id": citation.document_id,
            "claim_id": citation.claim_id,
            "raw_citation": citation.raw_citation,
            "citation_style": citation.citation_style,
            "sentence_text": citation.sentence_text,
            "page_number": citation.page_number,
            "paragraph_index": citation.paragraph_index,
            "mapped_reference_id": citation.mapped_reference_id,
            "mapping_confidence": citation.mapping_confidence,
            "created_at": _iso(citation.created_at),
        }

    def _link_dict(self, link: ClaimReferenceLink, *, include_details: bool = False) -> dict[str, Any]:
        reference = link.reference
        data = {
            "link_id": link.id,
            "claim_id": link.claim_id,
            "claim_text": link.claim.claim_text if link.claim else None,
            "citation_id": link.citation_id,
            "citation_text": link.citation.raw_citation if link.citation else None,
            "citation_style": link.citation.citation_style if link.citation else None,
            "reference_id": link.reference_id,
            "reference_title": _reference_title(reference),
            "doi": reference.extracted_doi if reference else None,
            "mapping_status": link.mapping_status,
            "mapping_confidence": link.mapping_confidence,
            "mapping_reason": link.mapping_reason,
            "created_at": _iso(link.created_at),
        }
        if include_details:
            data["claim"] = self._claim_summary(link.claim) if link.claim else None
            data["citation"] = self._citation_dict(link.citation) if link.citation else None
            data["reference"] = {
                "reference_id": reference.id,
                "reference_key": reference.reference_key,
                "raw_reference": reference.raw_reference,
                "extracted_title": reference.extracted_title,
                "extracted_authors": reference.extracted_authors,
                "extracted_year": reference.extracted_year,
                "extracted_doi": reference.extracted_doi,
                "doi_status": reference.doi_status,
                "metadata_status": reference.metadata_status,
                "metadata_match_score": reference.metadata_match_score,
            } if reference else None
        return data
