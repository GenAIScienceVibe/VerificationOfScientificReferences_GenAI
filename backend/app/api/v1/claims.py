from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.models.enums import ClaimType, MappingStatus
from app.services.claim_management import ClaimManagementService

router = APIRouter(tags=["claims"])


class ExtractClaimsRequest(BaseModel):
    mode: str = Field(default="citation_linked_only")
    sections: list[str] | None = None


@router.post("/documents/{document_id}/extract-claims")
async def extract_document_claims(
    request: Request,
    document_id: str,
    payload: ExtractClaimsRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or ExtractClaimsRequest()
    data = ClaimManagementService().extract_claims_for_document(
        document_id,
        db,
        mode=payload.mode,
        sections=payload.sections,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Citation-linked claims extracted")


@router.get("/documents/{document_id}/claims")
async def document_claims(
    request: Request,
    document_id: str,
    claim_type: ClaimType | None = Query(default=None),
    mapping_status: MappingStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = ClaimManagementService().list_claims(
        document_id,
        db,
        claim_type=claim_type.value if claim_type else None,
        mapping_status=mapping_status.value if mapping_status else None,
        page=page,
        page_size=page_size,
    )
    return success_response(request=request, data=data, message="Document claims returned")


@router.get("/claims/{claim_id}")
async def claim_details(request: Request, claim_id: str, db: Session = Depends(get_db)):
    data = ClaimManagementService().get_claim(claim_id, db)
    return success_response(request=request, data=data, message="Claim details returned")


@router.get("/documents/{document_id}/citations")
async def document_citations(
    request: Request,
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = ClaimManagementService().list_citations(document_id, db, page=page, page_size=page_size)
    return success_response(request=request, data=data, message="Document citations returned")


@router.get("/documents/{document_id}/claim-reference-links")
async def document_claim_reference_links(
    request: Request,
    document_id: str,
    mapping_status: MappingStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = ClaimManagementService().list_claim_reference_links(
        document_id,
        db,
        mapping_status=mapping_status.value if mapping_status else None,
        page=page,
        page_size=page_size,
    )
    return success_response(request=request, data=data, message="Claim-reference links returned")


@router.get("/documents/{document_id}/claim-reference-map")
async def document_claim_reference_map(
    request: Request,
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    data = ClaimManagementService().list_claim_reference_links(document_id, db, page=page, page_size=page_size)
    data["compatibility_endpoint"] = "claim-reference-map"
    return success_response(request=request, data=data, message="Claim-reference map returned")


@router.get("/claim-reference-links/{link_id}")
async def claim_reference_link_details(request: Request, link_id: str, db: Session = Depends(get_db)):
    data = ClaimManagementService().get_claim_reference_link(link_id, db)
    return success_response(request=request, data=data, message="Claim-reference link details returned")
