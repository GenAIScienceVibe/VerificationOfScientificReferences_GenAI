from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.reference_extraction import get_reference

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/{reference_id}")
async def reference_details(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = get_reference(reference_id, db)
    return success_response(request=request, data=data, message="Reference details returned")
