from __future__ import annotations

from pydantic import BaseModel


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


class ReadinessData(BaseModel):
    application: str
    database: str
    file_storage: str
    metadata_lookup: str
    rag_service: str
    genai_service: str
