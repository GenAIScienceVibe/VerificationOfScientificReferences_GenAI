from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.verification_cache import VerificationCacheService

router = APIRouter(tags=["verification-cache"])


class CheckCacheRequest(BaseModel):
    reference_id: str | None = None
    use_semantic_cache: bool = Field(default=False)
    force_refresh: bool = Field(default=False)


@router.post("/claims/{claim_id}/check-cache")
async def check_claim_cache(
    request: Request,
    claim_id: str,
    payload: CheckCacheRequest | None = None,
    db: Session = Depends(get_db),
):
    payload = payload or CheckCacheRequest()
    data = VerificationCacheService().check_claim_cache(
        claim_id,
        db,
        reference_id=payload.reference_id,
        use_semantic_cache=payload.use_semantic_cache,
        force_refresh=payload.force_refresh,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Verification cache decision returned")


@router.get("/claims/{claim_id}/cache-result")
async def get_claim_cache_result(request: Request, claim_id: str, db: Session = Depends(get_db)):
    data = VerificationCacheService().get_claim_cache_result(
        claim_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Claim cache result returned")
