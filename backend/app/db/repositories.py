from typing import List, Optional

from sqlalchemy.orm import Session

from .models import (
    CacheIndex,
    Claim,
    ClaimReferenceLink,
    Citation,
    Document,
    DocumentSection,
    EvidencePackage,
    PipelineRun,
    PipelineRunStep,
    Reference,
    Report,
    RetrievalChunk,
    RetrievalResult,
    SafetyCheck,
    SourceMetadata,
    UatSurvey,
    UserFeedback,
    VerificationResult,
)


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session


class DocumentRepository(BaseRepository):
    def get(self, document_id: str) -> Optional[Document]:
        return self.session.get(Document, document_id)

    def list(self, offset: int = 0, limit: int = 100, status: Optional[str] = None) -> List[Document]:
        q = self.session.query(Document)
        if status:
            q = q.filter(Document.status == status)
        return q.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    def count(self, status: Optional[str] = None) -> int:
        q = self.session.query(Document)
        if status:
            q = q.filter(Document.status == status)
        return q.count()

    def create(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document

    def delete(self, document_id: str) -> None:
        document = self.get(document_id)
        if document is not None:
            self.session.delete(document)


class DocumentSectionRepository(BaseRepository):
    def list_by_document(self, document_id: str) -> List[DocumentSection]:
        return (
            self.session.query(DocumentSection)
            .filter_by(document_id=document_id)
            .order_by(DocumentSection.order_index)
            .all()
        )

    def create(self, section: DocumentSection) -> DocumentSection:
        self.session.add(section)
        self.session.flush()
        return section


class ReferenceRepository(BaseRepository):
    def get(self, reference_id: str) -> Optional[Reference]:
        return self.session.get(Reference, reference_id)

    def list_by_document(
        self,
        document_id: str,
        doi_status: Optional[str] = None,
        metadata_status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Reference]:
        q = self.session.query(Reference).filter_by(document_id=document_id)
        if doi_status:
            q = q.filter(Reference.doi_status == doi_status)
        if metadata_status:
            q = q.filter(Reference.metadata_status == metadata_status)
        return q.order_by(Reference.position).offset(offset).limit(limit).all()

    def count_by_document(self, document_id: str) -> int:
        return self.session.query(Reference).filter_by(document_id=document_id).count()

    def create(self, reference: Reference) -> Reference:
        self.session.add(reference)
        self.session.flush()
        return reference


class SourceMetadataRepository(BaseRepository):
    def get_by_reference(self, reference_id: str) -> Optional[SourceMetadata]:
        return self.session.query(SourceMetadata).filter_by(reference_id=reference_id).one_or_none()

    def create(self, metadata: SourceMetadata) -> SourceMetadata:
        self.session.add(metadata)
        self.session.flush()
        return metadata


class ClaimRepository(BaseRepository):
    def get(self, claim_id: str) -> Optional[Claim]:
        return self.session.get(Claim, claim_id)

    def list_by_document(
        self,
        document_id: str,
        claim_type: Optional[str] = None,
        mapping_status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Claim]:
        q = self.session.query(Claim).filter_by(document_id=document_id)
        if claim_type:
            q = q.filter(Claim.claim_type == claim_type)
        if mapping_status:
            q = q.filter(Claim.mapping_status == mapping_status)
        return q.order_by(Claim.created_at).offset(offset).limit(limit).all()

    def count_by_document(self, document_id: str) -> int:
        return self.session.query(Claim).filter_by(document_id=document_id).count()

    def create(self, claim: Claim) -> Claim:
        self.session.add(claim)
        self.session.flush()
        return claim


class CitationRepository(BaseRepository):
    def get(self, citation_id: str) -> Optional[Citation]:
        return self.session.get(Citation, citation_id)

    def list_by_claim(self, claim_id: str) -> List[Citation]:
        return self.session.query(Citation).filter_by(claim_id=claim_id).all()

    def list_by_document(self, document_id: str) -> List[Citation]:
        return (
            self.session.query(Citation)
            .join(Claim)
            .filter(Claim.document_id == document_id)
            .all()
        )

    def create(self, citation: Citation) -> Citation:
        self.session.add(citation)
        self.session.flush()
        return citation


class ClaimReferenceLinkRepository(BaseRepository):
    def get(self, link_id: str) -> Optional[ClaimReferenceLink]:
        return self.session.get(ClaimReferenceLink, link_id)

    def list_by_document(self, document_id: str) -> List[ClaimReferenceLink]:
        return (
            self.session.query(ClaimReferenceLink)
            .join(Claim)
            .filter(Claim.document_id == document_id)
            .all()
        )

    def create(self, link: ClaimReferenceLink) -> ClaimReferenceLink:
        self.session.add(link)
        self.session.flush()
        return link


class EvidencePackageRepository(BaseRepository):
    def get_by_claim(self, claim_id: str) -> Optional[EvidencePackage]:
        return self.session.query(EvidencePackage).filter_by(claim_id=claim_id).one_or_none()

    def create(self, package: EvidencePackage) -> EvidencePackage:
        self.session.add(package)
        self.session.flush()
        return package


class RetrievalRepository(BaseRepository):
    def get_by_claim(self, claim_id: str) -> Optional[RetrievalResult]:
        return self.session.query(RetrievalResult).filter_by(claim_id=claim_id).one_or_none()

    def create(self, retrieval: RetrievalResult) -> RetrievalResult:
        self.session.add(retrieval)
        self.session.flush()
        return retrieval

    def add_chunk(self, chunk: RetrievalChunk) -> RetrievalChunk:
        self.session.add(chunk)
        self.session.flush()
        return chunk


class VerificationResultRepository(BaseRepository):
    def get(self, result_id: str) -> Optional[VerificationResult]:
        return self.session.get(VerificationResult, result_id)

    def list_by_document(
        self,
        document_id: str,
        support_status: Optional[str] = None,
        human_review_required: Optional[bool] = None,
        cache_source: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[VerificationResult]:
        q = (
            self.session.query(VerificationResult)
            .join(Claim)
            .filter(Claim.document_id == document_id)
        )
        if support_status:
            q = q.filter(VerificationResult.support_status == support_status)
        if human_review_required is not None:
            q = q.filter(VerificationResult.human_review_required == human_review_required)
        if cache_source:
            q = q.filter(VerificationResult.cache_source == cache_source)
        return q.offset(offset).limit(limit).all()

    def count_by_document(self, document_id: str, human_review_required: Optional[bool] = None) -> int:
        q = (
            self.session.query(VerificationResult)
            .join(Claim)
            .filter(Claim.document_id == document_id)
        )
        if human_review_required is not None:
            q = q.filter(VerificationResult.human_review_required == human_review_required)
        return q.count()

    def create(self, result: VerificationResult) -> VerificationResult:
        self.session.add(result)
        self.session.flush()
        return result


class SafetyCheckRepository(BaseRepository):
    def list_by_result(self, result_id: str) -> List[SafetyCheck]:
        return self.session.query(SafetyCheck).filter_by(verification_result_id=result_id).all()

    def create(self, check: SafetyCheck) -> SafetyCheck:
        self.session.add(check)
        self.session.flush()
        return check


class UserFeedbackRepository(BaseRepository):
    def get_by_result(self, result_id: str) -> Optional[UserFeedback]:
        return (
            self.session.query(UserFeedback)
            .filter_by(verification_result_id=result_id)
            .one_or_none()
        )

    def list_by_link(self, link_id: str) -> List[UserFeedback]:
        return self.session.query(UserFeedback).filter_by(claim_reference_link_id=link_id).all()

    def create(self, feedback: UserFeedback) -> UserFeedback:
        self.session.add(feedback)
        self.session.flush()
        return feedback


class CacheIndexRepository(BaseRepository):
    def get_by_claim(self, claim_id: str) -> Optional[CacheIndex]:
        return self.session.query(CacheIndex).filter_by(claim_id=claim_id).one_or_none()

    def create(self, cache: CacheIndex) -> CacheIndex:
        self.session.add(cache)
        self.session.flush()
        return cache


class PipelineRunRepository(BaseRepository):
    def get(self, pipeline_run_id: str) -> Optional[PipelineRun]:
        return self.session.get(PipelineRun, pipeline_run_id)

    def get_active_for_document(self, document_id: str) -> Optional[PipelineRun]:
        return (
            self.session.query(PipelineRun)
            .filter_by(document_id=document_id)
            .filter(PipelineRun.status.in_(["QUEUED", "RUNNING"]))
            .one_or_none()
        )

    def list_by_document(self, document_id: str) -> List[PipelineRun]:
        return (
            self.session.query(PipelineRun)
            .filter_by(document_id=document_id)
            .order_by(PipelineRun.created_at.desc())
            .all()
        )

    def create(self, run: PipelineRun) -> PipelineRun:
        self.session.add(run)
        self.session.flush()
        return run

    def add_step(self, step: PipelineRunStep) -> PipelineRunStep:
        self.session.add(step)
        self.session.flush()
        return step

    def list_steps(self, pipeline_run_id: str) -> List[PipelineRunStep]:
        return (
            self.session.query(PipelineRunStep)
            .filter_by(pipeline_run_id=pipeline_run_id)
            .order_by(PipelineRunStep.id)
            .all()
        )


class ReportRepository(BaseRepository):
    def get(self, report_id: str) -> Optional[Report]:
        return self.session.get(Report, report_id)

    def list_by_document(self, document_id: str) -> List[Report]:
        return (
            self.session.query(Report)
            .filter_by(document_id=document_id)
            .order_by(Report.created_at.desc())
            .all()
        )

    def create(self, report: Report) -> Report:
        self.session.add(report)
        self.session.flush()
        return report


class UatSurveyRepository(BaseRepository):
    def get(self, survey_id: str) -> Optional[UatSurvey]:
        return self.session.get(UatSurvey, survey_id)

    def list_by_document(self, document_id: str) -> List[UatSurvey]:
        return (
            self.session.query(UatSurvey)
            .filter_by(document_id=document_id)
            .order_by(UatSurvey.created_at.desc())
            .all()
        )

    def create(self, survey: UatSurvey) -> UatSurvey:
        self.session.add(survey)
        self.session.flush()
        return survey
