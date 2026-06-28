from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import PipelineRun, PipelineStep
from app.models.enums import PipelineStatus, PipelineStepStatus
from app.repositories.base import BaseRepository


class PipelineRepository(BaseRepository[PipelineRun]):
    model = PipelineRun

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    def create_run(
        self,
        *,
        document_id: str,
        mode: str = "STANDARD",
        status: str = PipelineStatus.QUEUED.value,
        commit: bool = True,
    ) -> PipelineRun:
        run = PipelineRun(document_id=document_id, mode=mode, status=status)
        return self.add(run, commit=commit)

    def create_step(
        self,
        *,
        pipeline_run_id: str,
        step_name: str,
        status: str = PipelineStepStatus.PENDING.value,
        commit: bool = True,
    ) -> PipelineStep:
        step = PipelineStep(pipeline_run_id=pipeline_run_id, step_name=step_name, status=status)
        self.db.add(step)
        if commit:
            self.db.commit()
            self.db.refresh(step)
        return step
