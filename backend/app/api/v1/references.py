from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.doi_metadata_lookup import MetadataLookupService
from app.services.reference_extraction import get_reference

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/{reference_id}")
async def reference_details(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = get_reference(reference_id, db)
    return success_response(request=request, data=data, message="Reference details returned")


@router.post("/{reference_id}/verify-doi")
async def verify_reference_doi(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().verify_reference_doi(
        reference_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Reference DOI metadata lookup completed")


@router.get("/{reference_id}/metadata")
async def reference_metadata(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().get_reference_metadata(reference_id, db)
    return success_response(request=request, data=data, message="Reference metadata returned")
