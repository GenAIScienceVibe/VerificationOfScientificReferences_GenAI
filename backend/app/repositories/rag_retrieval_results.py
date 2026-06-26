from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import RagRetrievalResult
from app.repositories.base import BaseRepository


class RagRetrievalResultRepository(BaseRepository[RagRetrievalResult]):
    """BE-9 persistence helper for RAG/ML retrieval attempts."""

    model = RagRetrievalResult

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def list_for_claim(
        self,
        claim_id: str,
        *,
        reference_id: str | None = None,
        latest_only: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[int, list[RagRetrievalResult]]:
        statement = (
            select(RagRetrievalResult)
            .options(
                selectinload(RagRetrievalResult.claim),
                selectinload(RagRetrievalResult.reference),
                selectinload(RagRetrievalResult.evidence_package),
            )
            .where(RagRetrievalResult.claim_id == claim_id)
        )
        if reference_id:
            statement = statement.where(RagRetrievalResult.reference_id == reference_id)
        results = list(self.db.scalars(statement.order_by(RagRetrievalResult.created_at.desc(), RagRetrievalResult.id.desc())).all())
        if latest_only:
            latest_by_key: dict[tuple[str, str | None], RagRetrievalResult] = {}
            for result in results:
                key = (result.reference_id, result.evidence_package_id)
                if key not in latest_by_key:
                    latest_by_key[key] = result
            results = list(latest_by_key.values())
        total = len(results)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        return total, results[(page - 1) * page_size : page * page_size]

    def latest_for_package(self, evidence_package_id: str) -> RagRetrievalResult | None:
        statement = (
            select(RagRetrievalResult)
            .where(RagRetrievalResult.evidence_package_id == evidence_package_id)
            .order_by(RagRetrievalResult.created_at.desc(), RagRetrievalResult.id.desc())
            .limit(1)
        )
        return self.db.scalar(statement)
