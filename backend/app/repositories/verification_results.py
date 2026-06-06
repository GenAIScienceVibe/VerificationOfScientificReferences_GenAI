from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import VerificationResult
from app.models.enums import CacheSource, EvidenceAvailability, SupportStatus
from app.repositories.base import BaseRepository


class VerificationResultRepository(BaseRepository[VerificationResult]):
    model = VerificationResult

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(
        self,
        *,
        document_id: str,
        claim_id: str,
        reference_id: str,
        support_status: str = SupportStatus.NEEDS_HUMAN_REVIEW.value,
        confidence: float | None = None,
        explanation: str | None = None,
        commit: bool = True,
    ) -> VerificationResult:
        result = VerificationResult(
            document_id=document_id,
            claim_id=claim_id,
            reference_id=reference_id,
            support_status=support_status,
            confidence=confidence,
            explanation=explanation,
            human_review_required=support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value,
            evidence_availability=EvidenceAvailability.SOURCE_UNAVAILABLE.value,
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        return self.add(result, commit=commit)
