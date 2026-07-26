from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.core.responses import success_response
from app.db.session import get_db, session_scope
from app.models import Document
from app.models.enums import SupportStatus
from app.services.verification_orchestrator import VerificationOrchestrator
from app.services.safety_policy import SafetyPolicyService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verification-orchestration"])


class PipelineRunRequest(BaseModel):
    mode: str = "FULL_VERIFICATION"
    use_cache: bool = True
    use_rag: bool = True
    use_genai_safety_review: bool = True
    generate_report: bool = False
    claim_ids: list[str] | None = None


def _run_pipeline_in_background(
    document_id: str,
    mode: str,
    use_cache: bool,
    use_rag: bool,
    use_genai_safety_review: bool,
    generate_report: bool,
    claim_ids: list[str] | None,
    request_id: str | None,
) -> None:
    """Run the full verification pipeline with its own DB session.

    BackgroundTasks execute after the HTTP response is sent, so we cannot
    reuse the request-scoped session from Depends(get_db) — it is already
    closed by then.  session_scope() opens a fresh session and commits or
    rolls back automatically.
    """
    with session_scope() as db:
        try:
            VerificationOrchestrator().run_document_verification(
                document_id,
                db,
                mode=mode,
                use_cache=use_cache,
                use_rag=use_rag,
                use_genai_safety_review=use_genai_safety_review,
                generate_report=generate_report,
                claim_ids=claim_ids,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Background pipeline run failed for document %s", document_id)
            raise


@router.post("/documents/{document_id}/pipeline-runs")
async def create_document_pipeline_run(
    request: Request,
    document_id: str,
    background_tasks: BackgroundTasks,
    payload: PipelineRunRequest | None = None,
    db: Session = Depends(get_db),
):
    """Start the verification pipeline and return immediately (202).

    The pipeline runs as a FastAPI BackgroundTask so Railway's proxy timeout
    cannot abort it mid-run.  The frontend polls /documents/{id}/status every
    2 s and navigates to /results once the status reaches a terminal state.
    """
    if db.get(Document, document_id) is None:
        raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document not found.", message="Document not found")

    payload = payload or PipelineRunRequest()
    background_tasks.add_task(
        _run_pipeline_in_background,
        document_id,
        payload.mode or "FULL_VERIFICATION",
        payload.use_cache,
        payload.use_rag,
        payload.use_genai_safety_review,
        payload.generate_report,
        payload.claim_ids,
        getattr(request.state, "request_id", None),
    )
    return success_response(
        request=request,
        data={"document_id": document_id, "status": "PROCESSING"},
        message="Verification pipeline started",
    )


@router.post("/documents/{document_id}/run-verification")
async def run_document_verification_compat(
    request: Request,
    document_id: str,
    payload: PipelineRunRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or PipelineRunRequest()
    data = VerificationOrchestrator().run_document_verification(
        document_id,
        db,
        mode=payload.mode or "FULL_VERIFICATION",
        use_cache=payload.use_cache,
        use_rag=payload.use_rag,
        use_genai_safety_review=payload.use_genai_safety_review,
        generate_report=payload.generate_report,
        claim_ids=payload.claim_ids,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Verification workflow completed")


@router.get("/pipeline-runs/{pipeline_run_id}")
async def get_pipeline_run(request: Request, pipeline_run_id: str, db: Session = Depends(get_db)):
    data = VerificationOrchestrator().get_pipeline_run(pipeline_run_id, db)
    return success_response(request=request, data=data, message="Pipeline run returned")


@router.get("/pipeline-runs/{pipeline_run_id}/steps")
async def get_pipeline_run_steps(request: Request, pipeline_run_id: str, db: Session = Depends(get_db)):
    data = VerificationOrchestrator().get_pipeline_steps(pipeline_run_id, db)
    return success_response(request=request, data=data, message="Pipeline run steps returned")


@router.get("/documents/{document_id}/verification-results")
async def get_document_verification_results(
    request: Request,
    document_id: str,
    support_status: SupportStatus | None = Query(default=None),
    human_review_required: bool | None = Query(default=None),
    cache_source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = VerificationOrchestrator().list_document_verification_results(
        document_id,
        db,
        support_status=support_status.value if support_status else None,
        human_review_required=human_review_required,
        cache_source=cache_source,
        page=page,
        page_size=page_size,
    )
    return success_response(request=request, data=data, message="Document verification results returned")


@router.get("/verification-results/{result_id}")
async def get_verification_result(request: Request, result_id: str, db: Session = Depends(get_db)):
    data = VerificationOrchestrator().get_verification_result(result_id, db)
    return success_response(request=request, data=data, message="Verification result returned")


@router.get("/verification-results/{result_id}/safety-checks")
async def get_verification_result_safety_checks(request: Request, result_id: str, db: Session = Depends(get_db)):
    data = SafetyPolicyService().get_safety_checks_for_result(result_id, db)
    return success_response(request=request, data=data, message="Verification result safety checks returned")


@router.get("/documents/{document_id}/safety-summary")
async def get_document_safety_summary(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = SafetyPolicyService().get_document_safety_summary(document_id, db)
    return success_response(request=request, data=data, message="Document safety summary returned")
