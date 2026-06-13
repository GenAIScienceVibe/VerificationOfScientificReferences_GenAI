from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceMetadata
from app.models.enums import MetadataStatus
from app.repositories.base import BaseRepository


class SourceMetadataRepository(BaseRepository[SourceMetadata]):
    model = SourceMetadata

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def get_latest_for_reference(self, reference_id: str) -> SourceMetadata | None:
        statement = (
            select(SourceMetadata)
            .where(SourceMetadata.reference_id == reference_id)
            .order_by(SourceMetadata.updated_at.desc(), SourceMetadata.created_at.desc())
            .limit(1)
        )
        return self.db.scalars(statement).first()

    def find_success_by_doi(self, doi: str) -> SourceMetadata | None:
        normalized = doi.lower().strip()
        statement = (
            select(SourceMetadata)
            .where(
                SourceMetadata.doi == normalized,
                SourceMetadata.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value,
            )
            .order_by(SourceMetadata.updated_at.desc(), SourceMetadata.created_at.desc())
            .limit(1)
        )
        return self.db.scalars(statement).first()

    def upsert_for_reference(
        self,
        *,
        reference_id: str,
        doi: str | None,
        title: str | None,
        authors: str | None,
        year: int | None,
        venue: str | None,
        publisher: str | None,
        abstract: str | None,
        url: str | None,
        lookup_source: str,
        lookup_status: str,
        raw_metadata_json: dict | list | None,
        title_match: float | None,
        author_match: float | None,
        year_match: bool | None,
        doi_match: bool | None,
        metadata_match_score: float | None,
        commit: bool = True,
    ) -> SourceMetadata:
        record = self.get_latest_for_reference(reference_id)
        if record is None:
            record = SourceMetadata(reference_id=reference_id)
            self.db.add(record)
        record.doi = doi
        record.title = title
        record.authors = authors
        record.year = year
        record.venue = venue
        record.publisher = publisher
        record.abstract = abstract
        record.url = url
        record.lookup_source = lookup_source
        record.lookup_status = lookup_status
        record.raw_metadata_json = raw_metadata_json
        record.title_match = title_match
        record.author_match = author_match
        record.year_match = year_match
        record.doi_match = doi_match
        record.metadata_match_score = metadata_match_score
        if commit:
            self.db.commit()
            self.db.refresh(record)
        return record
