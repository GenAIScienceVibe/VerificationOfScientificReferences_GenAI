from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create(
        self,
        *,
        filename: str,
        title: str | None,
        upload_type: str,
        status: str,
        file_size_bytes: int | None = None,
        file_storage_path: str | None = None,
        raw_text: str | None = None,
        cleaned_text: str | None = None,
        commit: bool = True,
    ) -> Document:
        document = Document(
            filename=filename,
            title=title,
            upload_type=upload_type,
            status=status,
            file_size_bytes=file_size_bytes,
            file_storage_path=file_storage_path,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
        )
        return self.add(document, commit=commit)

    def list_by_status(self, status: str) -> list[Document]:
        return list(self.db.scalars(select(Document).where(Document.status == status)).all())
