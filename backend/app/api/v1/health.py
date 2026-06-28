from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.responses import success_response
from app.db.session import check_database_ready

router = APIRouter(prefix="/health", tags=["health"])


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@router.get("")
async def health(request: Request):
    settings = get_settings()
    data = {
        "status": "OK",
        "service": settings.service_name,
        "version": settings.app_version,
        "timestamp": _now(),
    }
    return success_response(request=request, data=data, message="Backend is healthy")


@router.get("/readiness")
async def readiness(request: Request):
    settings = get_settings()
    db_ready, db_status = check_database_ready()

    try:
        settings.file_storage_dir.mkdir(parents=True, exist_ok=True)
        marker = settings.file_storage_dir / ".readiness_check"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        file_storage_status = "ready"
    except Exception as exc:  # pragma: no cover - failure path depends on file permissions
        file_storage_status = f"unavailable: {exc.__class__.__name__}"

    data = {
        "application": "ready",
        "database": db_status if db_ready else db_status,
        "file_storage": file_storage_status,
        "metadata_lookup": "mock_ready" if settings.metadata_mock_mode else ("enabled" if settings.metadata_lookup_enabled else "disabled"),
        "rag_service": "mock_ready" if settings.rag_mock_mode else ("configured" if settings.is_rag_configured else "not_configured"),
        "genai_service": "mock_ready" if settings.genai_mock_mode else ("configured" if settings.is_genai_configured else "not_configured"),
        "demo_mode": settings.demo_mode,
        "phase": "BE-13",
    }
    return success_response(request=request, data=data, message="Backend readiness checked")
