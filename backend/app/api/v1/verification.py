from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.verification_orchestrator import VerificationOrchestrator
from app.services.safety_policy import SafetyPolicyService

router = APIRouter(tags=["verification-orchestration"])


class PipelineRunRequest(BaseModel):
    mode: str = "FULL_VERIFICATION"
    use_cache: bool = True
    use_rag: bool = True
    use_genai_safety_review: bool = True
    generate_report: bool = False


@router.post("/documents/{document_id}/pipeline-runs")
async def create_document_pipeline_run(
    request: Request,
    document_id: str,
    payload: PipelineRunRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or PipelineRunRequest()
    data = VerificationOrchestrator().run_document_verification(
        document_id,
        db,
        mode=payload.mode,
        use_cache=payload.use_cache,
        use_rag=payload.use_rag,
        use_genai_safety_review=payload.use_genai_safety_review,
        generate_report=payload.generate_report,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Verification pipeline run completed")


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
    support_status: str | None = Query(default=None),
    human_review_required: bool | None = Query(default=None),
    cache_source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = VerificationOrchestrator().list_document_verification_results(
        document_id,
        db,
        support_status=support_status,
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
