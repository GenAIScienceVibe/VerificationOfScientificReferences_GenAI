from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import claims, documents, health, references

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(references.router)
api_router.include_router(claims.router)
