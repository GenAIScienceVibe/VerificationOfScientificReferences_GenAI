
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.report_generation import DocumentSummaryService, FeedbackService, ReportService, UatSurveyService

router = APIRouter(tags=["reports-feedback-uat"])


class GenerateReportRequest(BaseModel):
    format: str = Field(default="HTML")
    include_evidence_chunks: bool = True
    include_human_review_items: bool = True
    include_limitations: bool = True


class VerificationFeedbackRequest(BaseModel):
    user_label: str | None = None
    user_comment: str | None = None
    user_role: str | None = None


class MappingFeedbackRequest(BaseModel):
    feedback_type: str = Field(default="OTHER")
    suggested_reference_id: str | None = None
    comment: str | None = None
    user_role: str | None = None


class UatSurveyRequest(BaseModel):
    document_id: str
    participant_role: str | None = None
    ease_of_use_rating: int = Field(ge=1, le=5)
    result_clarity_rating: int = Field(ge=1, le=5)
    trust_rating: int = Field(ge=1, le=5)
    usefulness_rating: int = Field(ge=1, le=5)
    comments: str | None = None


@router.get("/documents/{document_id}/summary")
async def document_summary(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = DocumentSummaryService().get_document_summary(document_id, db)
    return success_response(request=request, data=data, message="Document verification summary returned")


@router.post("/documents/{document_id}/reports")
async def generate_document_report(
    request: Request,
    document_id: str,
    payload: GenerateReportRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or GenerateReportRequest()
    data = ReportService().generate_report(
        document_id,
        db,
        report_format=payload.format,
        include_evidence_chunks=payload.include_evidence_chunks,
        include_human_review_items=payload.include_human_review_items,
        include_limitations=payload.include_limitations,
    )
    return success_response(request=request, data=data, message="Document verification report generated")


@router.get("/documents/{document_id}/report")
async def get_latest_document_report(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = ReportService().get_latest_report_for_document(document_id, db)
    return success_response(request=request, data=data, message="Latest document report returned")


@router.get("/reports/{report_id}")
async def get_report(request: Request, report_id: str, db: Session = Depends(get_db)):
    data = ReportService().get_report(report_id, db)
    return success_response(request=request, data=data, message="Report returned")


@router.get("/reports/{report_id}/download")
async def download_report(
    request: Request,
    report_id: str,
    format: str = Query(default="HTML"),
    db: Session = Depends(get_db),
):
    data = ReportService().download_report(report_id, format, db)
    return success_response(request=request, data=data, message="Report download returned")


@router.post("/verification-results/{result_id}/feedback")
async def submit_verification_feedback(
    request: Request,
    result_id: str,
    payload: VerificationFeedbackRequest,
    db: Session = Depends(get_db),
):
    data = FeedbackService().submit_verification_feedback(
        result_id,
        db,
        user_label=payload.user_label,
        user_comment=payload.user_comment,
        user_role=payload.user_role,
    )
    return success_response(request=request, data=data, message="Verification result feedback stored")


@router.post("/claim-reference-links/{link_id}/feedback")
async def submit_claim_reference_mapping_feedback(
    request: Request,
    link_id: str,
    payload: MappingFeedbackRequest,
    db: Session = Depends(get_db),
):
    data = FeedbackService().submit_mapping_feedback(
        link_id,
        db,
        feedback_type=payload.feedback_type,
        suggested_reference_id=payload.suggested_reference_id,
        comment=payload.comment,
        user_role=payload.user_role,
    )
    return success_response(request=request, data=data, message="Claim-reference mapping feedback stored")


@router.post("/uat/surveys")
async def submit_uat_survey(request: Request, payload: UatSurveyRequest, db: Session = Depends(get_db)):
    data = UatSurveyService().submit_survey(
        db,
        document_id=payload.document_id,
        participant_role=payload.participant_role,
        ease_of_use_rating=payload.ease_of_use_rating,
        result_clarity_rating=payload.result_clarity_rating,
        trust_rating=payload.trust_rating,
        usefulness_rating=payload.usefulness_rating,
        comments=payload.comments,
    )
    return success_response(request=request, data=data, message="UAT survey response stored")
