from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.rag_ml_integration import RagRetrievalService

router = APIRouter(tags=["rag-retrieval"])


class RetrieveEvidenceRequest(BaseModel):
    reference_id: str | None = None
    evidence_package_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    force_refresh: bool = False
    use_mock: bool | None = None


@router.post("/claims/{claim_id}/retrieve-evidence")
async def retrieve_claim_evidence(
    request: Request,
    claim_id: str,
    payload: RetrieveEvidenceRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or RetrieveEvidenceRequest()
    data = RagRetrievalService().retrieve_evidence_for_claim(
        claim_id,
        db,
        reference_id=payload.reference_id,
        evidence_package_id=payload.evidence_package_id,
        top_k=payload.top_k,
        force_refresh=payload.force_refresh,
        use_mock=payload.use_mock,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="RAG evidence retrieval completed")


@router.get("/claims/{claim_id}/retrieval-results")
async def get_claim_retrieval_results(
    request: Request,
    claim_id: str,
    reference_id: str | None = Query(default=None),
    latest_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = RagRetrievalService().list_claim_retrieval_results(
        claim_id,
        db,
        reference_id=reference_id,
        latest_only=latest_only,
        page=page,
        page_size=page_size,
    )
    return success_response(request=request, data=data, message="Claim retrieval results returned")
