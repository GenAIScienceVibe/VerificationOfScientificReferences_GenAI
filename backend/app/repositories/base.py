from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Small persistence helper used in BE-2.

    Repositories stay intentionally thin: they create/read database records only.
    Business workflows are deferred to later backend phases.
    """

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, record_id: str) -> ModelT | None:
        return self.db.get(self.model, record_id)

    def add(self, entity: ModelT, *, commit: bool = True) -> ModelT:
        self.db.add(entity)
        if commit:
            self.db.commit()
            self.db.refresh(entity)
        return entity
