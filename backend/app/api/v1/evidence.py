from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.evidence_service import EvidencePackageService

router = APIRouter(tags=["evidence"])


@router.post("/documents/{document_id}/prepare-evidence")
async def prepare_document_evidence(request: Request, document_id: str, db: Session = Depends(get_db)):
    data = EvidencePackageService().prepare_evidence_for_document(
        document_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Evidence packages prepared")


@router.get("/claims/{claim_id}/evidence-package")
async def claim_evidence_package(request: Request, claim_id: str, db: Session = Depends(get_db)):
    data = EvidencePackageService().get_evidence_package_for_claim(claim_id, db)
    return success_response(request=request, data=data, message="Evidence package returned")
