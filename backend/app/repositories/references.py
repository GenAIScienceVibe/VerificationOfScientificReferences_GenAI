from __future__ import annotations

from sqlalchemy import delete, func, select
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
        extracted_authors: str | None = None,
        extracted_year: int | None = None,
        extracted_doi: str | None = None,
        doi_status: str | None = None,
        metadata_status: str | None = None,
        metadata_match_score: float | None = None,
        commit: bool = True,
    ) -> Reference:
        reference = Reference(
            document_id=document_id,
            raw_reference=raw_reference,
            reference_key=reference_key,
            extracted_title=extracted_title,
            extracted_authors=extracted_authors,
            extracted_year=extracted_year,
            extracted_doi=extracted_doi,
            doi_status=doi_status or "MISSING",
            metadata_status=metadata_status or "NOT_LOOKED_UP",
            metadata_match_score=metadata_match_score,
        )
        return self.add(reference, commit=commit)

    def replace_for_document(self, *, document_id: str, references: list[dict], commit: bool = True) -> list[Reference]:
        self.db.execute(delete(Reference).where(Reference.document_id == document_id))
        created: list[Reference] = []
        for item in references:
            reference = Reference(document_id=document_id, **item)
            self.db.add(reference)
            created.append(reference)
        if commit:
            self.db.commit()
            for reference in created:
                self.db.refresh(reference)
        return created

    def list_for_document(self, document_id: str) -> list[Reference]:
        statement = select(Reference).where(Reference.document_id == document_id).order_by(Reference.created_at, Reference.id)
        return list(self.db.scalars(statement).all())

    def list_for_document_paginated(
        self,
        *,
        document_id: str,
        doi_status: str | None = None,
        metadata_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Reference], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        filters = [Reference.document_id == document_id]
        if doi_status:
            filters.append(Reference.doi_status == doi_status)
        if metadata_status:
            filters.append(Reference.metadata_status == metadata_status)

        total_statement = select(func.count()).select_from(Reference).where(*filters)
        total = int(self.db.scalar(total_statement) or 0)
        statement = (
            select(Reference)
            .where(*filters)
            .order_by(Reference.created_at, Reference.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement).all()), total
