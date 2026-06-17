from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.cache_service import VerificationCacheService

router = APIRouter(tags=["cache"])


@router.post("/claims/{claim_id}/check-cache")
async def check_claim_cache(
    request: Request,
    claim_id: str,
    reference_id: str | None = Query(default=None, description="Optionally scope the cache check to a specific reference"),
    db: Session = Depends(get_db),
):
    data = VerificationCacheService().check_cache(
        claim_id,
        db,
        reference_id=reference_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Cache check completed")


@router.get("/claims/{claim_id}/cache-result")
async def claim_cache_result(
    request: Request,
    claim_id: str,
    db: Session = Depends(get_db),
):
    data = VerificationCacheService().get_cache_result(claim_id, db)
    return success_response(request=request, data=data, message="Cache result returned")
