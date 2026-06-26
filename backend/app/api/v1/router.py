from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import cache, claims, documents, evidence, health, references, retrieval, verification

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(references.router)
api_router.include_router(claims.router)
api_router.include_router(evidence.router)
api_router.include_router(cache.router)
api_router.include_router(retrieval.router)

api_router.include_router(verification.router)
