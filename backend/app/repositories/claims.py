from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim
from app.models.enums import ClaimType
from app.repositories.base import BaseRepository


class ClaimRepository(BaseRepository[Claim]):
    model = Claim

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(
        self,
        *,
        document_id: str,
        claim_text: str,
        claim_type: str = ClaimType.UNKNOWN.value,
        section_name: str | None = None,
        commit: bool = True,
    ) -> Claim:
        claim = Claim(document_id=document_id, claim_text=claim_text, claim_type=claim_type, section_name=section_name)
        return self.add(claim, commit=commit)

    def list_for_document(self, document_id: str) -> list[Claim]:
        return list(self.db.scalars(select(Claim).where(Claim.document_id == document_id)).all())
