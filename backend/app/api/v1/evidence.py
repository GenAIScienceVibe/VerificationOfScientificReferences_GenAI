from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.evidence_package_builder import EvidencePackageBuilder

router = APIRouter(tags=["evidence"])


@router.post("/documents/{document_id}/prepare-evidence")
async def prepare_document_evidence(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = EvidencePackageBuilder().prepare_evidence_for_document(
        document_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Evidence packages prepared")


@router.get("/claims/{claim_id}/evidence-package")
async def claim_evidence_package(request: Request, claim_id: str, db: Session = Depends(get_db)):
    data = EvidencePackageBuilder().get_claim_evidence_package(claim_id, db)
    return success_response(request=request, data=data, message="Claim evidence package returned")


@router.get("/documents/{document_id}/evidence-packages")
async def document_evidence_packages(
    request: Request,
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = EvidencePackageBuilder().list_document_evidence_packages(document_id, db, page=page, page_size=page_size)
    return success_response(request=request, data=data, message="Document evidence packages returned")
