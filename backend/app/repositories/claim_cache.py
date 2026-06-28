from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ClaimCacheIndex
from app.repositories.base import BaseRepository


class ClaimCacheRepository(BaseRepository[ClaimCacheIndex]):
    """BE-8 persistence helper for verification cache rows."""

    model = ClaimCacheIndex

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def find_exact_candidates(
        self,
        *,
        normalized_claim_hash: str,
        doi: str,
        embedding_model_version: str,
        prompt_version: str,
        verification_policy_version: str,
        evidence_version: str | None = None,
        reference_id: str | None = None,
    ) -> list[ClaimCacheIndex]:
        statement = (
            select(ClaimCacheIndex)
            .options(selectinload(ClaimCacheIndex.verification_result), selectinload(ClaimCacheIndex.reference))
            .where(ClaimCacheIndex.normalized_claim_hash == normalized_claim_hash)
            .where(ClaimCacheIndex.doi == doi)
            .where(ClaimCacheIndex.embedding_model_version == embedding_model_version)
            .where(ClaimCacheIndex.prompt_version == prompt_version)
            .where(ClaimCacheIndex.verification_policy_version == verification_policy_version)
        )
        if evidence_version:
            statement = statement.where(ClaimCacheIndex.evidence_version == evidence_version)
        if reference_id:
            statement = statement.where(ClaimCacheIndex.reference_id == reference_id)
        statement = statement.order_by(ClaimCacheIndex.created_at.desc(), ClaimCacheIndex.id.desc())
        return list(self.db.scalars(statement).all())

    def list_for_doi(self, *, doi: str, verification_policy_version: str | None = None) -> list[ClaimCacheIndex]:
        statement = (
            select(ClaimCacheIndex)
            .options(selectinload(ClaimCacheIndex.verification_result), selectinload(ClaimCacheIndex.reference))
            .where(ClaimCacheIndex.doi == doi)
            .order_by(ClaimCacheIndex.created_at.desc(), ClaimCacheIndex.id.desc())
        )
        if verification_policy_version:
            statement = statement.where(ClaimCacheIndex.verification_policy_version == verification_policy_version)
        return list(self.db.scalars(statement).all())

    def get_by_verification_result(self, verification_result_id: str) -> ClaimCacheIndex | None:
        statement = select(ClaimCacheIndex).where(ClaimCacheIndex.verification_result_id == verification_result_id)
        return self.db.scalars(statement).first()

    def find_existing_key(
        self,
        *,
        normalized_claim_hash: str,
        doi: str,
        reference_id: str,
        evidence_version: str,
        embedding_model_version: str,
        prompt_version: str,
        verification_policy_version: str,
    ) -> ClaimCacheIndex | None:
        statement = (
            select(ClaimCacheIndex)
            .where(ClaimCacheIndex.normalized_claim_hash == normalized_claim_hash)
            .where(ClaimCacheIndex.doi == doi)
            .where(ClaimCacheIndex.reference_id == reference_id)
            .where(ClaimCacheIndex.evidence_version == evidence_version)
            .where(ClaimCacheIndex.embedding_model_version == embedding_model_version)
            .where(ClaimCacheIndex.prompt_version == prompt_version)
            .where(ClaimCacheIndex.verification_policy_version == verification_policy_version)
        )
        return self.db.scalars(statement).first()
