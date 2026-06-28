from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import EvidencePackage
from app.repositories.base import BaseRepository


class EvidencePackageRepository(BaseRepository[EvidencePackage]):
    """Thin BE-7 persistence helper for evidence packages."""

    model = EvidencePackage

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def delete_for_document(self, document_id: str) -> None:
        self.db.execute(delete(EvidencePackage).where(EvidencePackage.document_id == document_id))
        self.db.flush()

    def list_for_document(self, document_id: str) -> list[EvidencePackage]:
        statement = (
            select(EvidencePackage)
            .options(
                selectinload(EvidencePackage.claim),
                selectinload(EvidencePackage.reference),
                selectinload(EvidencePackage.citation),
                selectinload(EvidencePackage.claim_reference_link),
            )
            .where(EvidencePackage.document_id == document_id)
            .order_by(EvidencePackage.created_at, EvidencePackage.id)
        )
        return list(self.db.scalars(statement).all())

    def list_for_claim(self, claim_id: str) -> list[EvidencePackage]:
        statement = (
            select(EvidencePackage)
            .options(
                selectinload(EvidencePackage.claim),
                selectinload(EvidencePackage.reference),
                selectinload(EvidencePackage.citation),
                selectinload(EvidencePackage.claim_reference_link),
            )
            .where(EvidencePackage.claim_id == claim_id)
            .order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc())
        )
        return list(self.db.scalars(statement).all())
