from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Document, DocumentSection
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
        pages_count: int = 0,
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
            pages_count=pages_count,
        )
        return self.add(document, commit=commit)

    def get_with_sections(self, document_id: str) -> Document | None:
        statement = select(Document).options(selectinload(Document.sections)).where(Document.id == document_id)
        return self.db.scalar(statement)

    def list_by_status(self, status: str) -> list[Document]:
        return list(self.db.scalars(select(Document).where(Document.status == status)).all())


class DocumentSectionRepository(BaseRepository[DocumentSection]):
    model = DocumentSection

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def replace_for_document(self, *, document_id: str, sections: list[dict], commit: bool = True) -> list[DocumentSection]:
        existing = list(self.db.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id)).all())
        for section in existing:
            self.db.delete(section)
        created: list[DocumentSection] = []
        for item in sections:
            section = DocumentSection(
                document_id=document_id,
                name=item["name"],
                order_index=item.get("order_index", len(created)),
                text=item.get("text"),
                text_preview=item.get("text_preview"),
                page_start=item.get("page_start"),
                page_end=item.get("page_end"),
            )
            self.db.add(section)
            created.append(section)
        if commit:
            self.db.commit()
            for section in created:
                self.db.refresh(section)
        return created

    def list_for_document(self, document_id: str) -> list[DocumentSection]:
        statement = select(DocumentSection).where(DocumentSection.document_id == document_id).order_by(DocumentSection.order_index)
        return list(self.db.scalars(statement).all())
