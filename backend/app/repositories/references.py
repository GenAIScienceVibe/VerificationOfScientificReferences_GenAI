from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Reference
from app.repositories.base import BaseRepository


class ReferenceRepository(BaseRepository[Reference]):
    model = Reference

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(
        self,
        *,
        document_id: str,
        raw_reference: str,
        reference_key: str | None = None,
        extracted_title: str | None = None,
        extracted_doi: str | None = None,
        commit: bool = True,
    ) -> Reference:
        reference = Reference(
            document_id=document_id,
            raw_reference=raw_reference,
            reference_key=reference_key,
            extracted_title=extracted_title,
            extracted_doi=extracted_doi,
        )
        return self.add(reference, commit=commit)

    def list_for_document(self, document_id: str) -> list[Reference]:
        return list(self.db.scalars(select(Reference).where(Reference.document_id == document_id)).all())
