from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()


class Settings(BaseModel):
    """Environment-driven application settings for BE-1."""

    app_name: str = Field(default="verifAI / RefCheck AI Backend", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    database_url: str = Field(default="sqlite:///./data/refcheck_be1.db", alias="DATABASE_URL")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    file_storage_dir: Path = Field(default=Path("./data/uploads"), alias="FILE_STORAGE_DIR")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="meta-llama/llama-4-scout-17b-16e-instruct", alias="GROQ_MODEL")
    genai_provider: str = Field(default="groq", alias="GENAI_PROVIDER")
    claim_extraction_mode: str = Field(default="local_deterministic", alias="CLAIM_EXTRACTION_MODE")
    claim_extraction_prompt_version: str = Field(default="be6-claim-extraction-v1", alias="CLAIM_EXTRACTION_PROMPT_VERSION")
    rag_service_url: str | None = Field(default=None, alias="RAG_SERVICE_URL")
    metadata_service_timeout_seconds: float = Field(default=10.0, alias="METADATA_SERVICE_TIMEOUT_SECONDS")
    metadata_lookup_enabled: bool = Field(default=True, alias="METADATA_LOOKUP_ENABLED")
    crossref_base_url: str = Field(default="https://api.crossref.org", alias="CROSSREF_BASE_URL")
    doi_resolver_base_url: str = Field(default="https://doi.org", alias="DOI_RESOLVER_BASE_URL")
    openalex_base_url: str = Field(default="https://api.openalex.org", alias="OPENALEX_BASE_URL")
    metadata_max_retries: int = Field(default=2, alias="METADATA_MAX_RETRIES")
    crossref_mailto: str | None = Field(default=None, alias="CROSSREF_MAILTO")
    metadata_user_agent: str = Field(default="verifai-refcheck-backend/1.0.0", alias="METADATA_USER_AGENT")
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")
    enable_raw_text_debug_endpoint: bool = Field(default=False, alias="ENABLE_RAW_TEXT_DEBUG_ENDPOINT")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        raw = value.strip()
        if raw.startswith("["):
            return [str(item).strip() for item in json.loads(raw)]
        return [item.strip() for item in raw.split(",") if item.strip()]

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip() or "/api/v1"
        return value if value.startswith("/") else f"/{value}"

    @property
    def service_name(self) -> str:
        return "refcheck-backend"

    @property
    def is_genai_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def is_rag_configured(self) -> bool:
        return bool(self.rag_service_url)


def _read_env() -> dict[str, object]:
    keys = {
        "APP_NAME",
        "APP_VERSION",
        "ENVIRONMENT",
        "API_PREFIX",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "LOG_LEVEL",
        "FILE_STORAGE_DIR",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GENAI_PROVIDER",
        "CLAIM_EXTRACTION_MODE",
        "CLAIM_EXTRACTION_PROMPT_VERSION",
        "RAG_SERVICE_URL",
        "METADATA_SERVICE_TIMEOUT_SECONDS",
        "METADATA_LOOKUP_ENABLED",
        "CROSSREF_BASE_URL",
        "DOI_RESOLVER_BASE_URL",
        "OPENALEX_BASE_URL",
        "METADATA_MAX_RETRIES",
        "CROSSREF_MAILTO",
        "METADATA_USER_AGENT",
        "MAX_UPLOAD_SIZE_BYTES",
        "ENABLE_RAW_TEXT_DEBUG_ENDPOINT",
    }
    return {key: value for key in keys if (value := os.getenv(key)) is not None}


@lru_cache
def get_settings() -> Settings:
    return Settings(**_read_env())
