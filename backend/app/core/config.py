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
    rag_service_url: str | None = Field(default="http://localhost:9000", alias="RAG_SERVICE_URL")
    rag_service_enabled: bool = Field(default=True, alias="RAG_SERVICE_ENABLED")
    rag_service_timeout_seconds: float = Field(default=30.0, alias="RAG_SERVICE_TIMEOUT_SECONDS")
    rag_service_max_retries: int = Field(default=1, alias="RAG_SERVICE_MAX_RETRIES")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_min_similarity_threshold: float = Field(default=0.60, alias="RAG_MIN_SIMILARITY_THRESHOLD")
    rag_mock_mode: bool = Field(default=True, alias="RAG_MOCK_MODE")
    rag_request_version: str = Field(default="rag-request-v1", alias="RAG_REQUEST_VERSION")
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
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")
    metadata_mock_mode: bool = Field(default=False, alias="METADATA_MOCK_MODE")
    genai_mock_mode: bool = Field(default=True, alias="GENAI_MOCK_MODE")
    embedding_model_version: str = Field(default="embedding-v1", alias="EMBEDDING_MODEL_VERSION")
    verification_prompt_version: str = Field(default="verify-v1", alias="VERIFICATION_PROMPT_VERSION")
    verification_policy_version: str = Field(default="policy-v1", alias="VERIFICATION_POLICY_VERSION")
    cache_enabled: bool = Field(default=True, alias="CACHE_ENABLED")
    cache_exact_enabled: bool = Field(default=True, alias="CACHE_EXACT_ENABLED")
    cache_semantic_enabled: bool = Field(default=False, alias="CACHE_SEMANTIC_ENABLED")
    cache_high_similarity_threshold: float = Field(default=0.92, alias="CACHE_HIGH_SIMILARITY_THRESHOLD")
    cache_medium_similarity_threshold: float = Field(default=0.80, alias="CACHE_MEDIUM_SIMILARITY_THRESHOLD")
    cache_min_confidence_to_reuse: float = Field(default=0.75, alias="CACHE_MIN_CONFIDENCE_TO_REUSE")
    cache_ttl_days: int = Field(default=180, alias="CACHE_TTL_DAYS")
    cache_require_same_doi: bool = Field(default=True, alias="CACHE_REQUIRE_SAME_DOI")
    cache_require_same_policy_version: bool = Field(default=True, alias="CACHE_REQUIRE_SAME_POLICY_VERSION")
    cache_require_same_reference: bool = Field(default=False, alias="CACHE_REQUIRE_SAME_REFERENCE")
    cache_evidence_version: str = Field(default="evidence-v1", alias="CACHE_EVIDENCE_VERSION")

    # BE-11 deterministic safety/confidence policy settings.
    safety_min_genai_confidence: float = Field(default=0.60, alias="SAFETY_MIN_GENAI_CONFIDENCE")
    safety_min_strong_similarity: float = Field(default=0.80, alias="SAFETY_MIN_STRONG_SIMILARITY")
    safety_min_acceptable_similarity: float = Field(default=0.60, alias="SAFETY_MIN_ACCEPTABLE_SIMILARITY")
    safety_low_similarity_threshold: float = Field(default=0.60, alias="SAFETY_LOW_SIMILARITY_THRESHOLD")
    safety_require_valid_doi_for_supported: bool = Field(default=True, alias="SAFETY_REQUIRE_VALID_DOI_FOR_SUPPORTED")
    safety_require_evidence_for_supported: bool = Field(default=True, alias="SAFETY_REQUIRE_EVIDENCE_FOR_SUPPORTED")
    safety_flag_metadata_only_supported: bool = Field(default=True, alias="SAFETY_FLAG_METADATA_ONLY_SUPPORTED")
    safety_flag_source_unavailable: bool = Field(default=True, alias="SAFETY_FLAG_SOURCE_UNAVAILABLE")
    safety_enable_genai_rag_conflict_check: bool = Field(default=True, alias="SAFETY_ENABLE_GENAI_RAG_CONFLICT_CHECK")
    safety_max_confidence_with_metadata_only: float = Field(default=0.70, alias="SAFETY_MAX_CONFIDENCE_WITH_METADATA_ONLY")
    safety_max_confidence_with_source_unavailable: float = Field(default=0.40, alias="SAFETY_MAX_CONFIDENCE_WITH_SOURCE_UNAVAILABLE")
    safety_max_confidence_with_low_similarity: float = Field(default=0.55, alias="SAFETY_MAX_CONFIDENCE_WITH_LOW_SIMILARITY")
    safety_policy_version: str = Field(default="policy-v1", alias="SAFETY_POLICY_VERSION")

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
        return bool(self.rag_service_url) and bool(self.rag_service_enabled)


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
        "RAG_SERVICE_ENABLED",
        "RAG_SERVICE_TIMEOUT_SECONDS",
        "RAG_SERVICE_MAX_RETRIES",
        "RAG_TOP_K",
        "RAG_MIN_SIMILARITY_THRESHOLD",
        "RAG_MOCK_MODE",
        "RAG_REQUEST_VERSION",
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
        "DEMO_MODE",
        "METADATA_MOCK_MODE",
        "GENAI_MOCK_MODE",
        "EMBEDDING_MODEL_VERSION",
        "VERIFICATION_PROMPT_VERSION",
        "VERIFICATION_POLICY_VERSION",
        "CACHE_ENABLED",
        "CACHE_EXACT_ENABLED",
        "CACHE_SEMANTIC_ENABLED",
        "CACHE_HIGH_SIMILARITY_THRESHOLD",
        "CACHE_MEDIUM_SIMILARITY_THRESHOLD",
        "CACHE_MIN_CONFIDENCE_TO_REUSE",
        "CACHE_TTL_DAYS",
        "CACHE_REQUIRE_SAME_DOI",
        "CACHE_REQUIRE_SAME_POLICY_VERSION",
        "CACHE_REQUIRE_SAME_REFERENCE",
        "CACHE_EVIDENCE_VERSION",
        "SAFETY_MIN_GENAI_CONFIDENCE",
        "SAFETY_MIN_STRONG_SIMILARITY",
        "SAFETY_MIN_ACCEPTABLE_SIMILARITY",
        "SAFETY_LOW_SIMILARITY_THRESHOLD",
        "SAFETY_REQUIRE_VALID_DOI_FOR_SUPPORTED",
        "SAFETY_REQUIRE_EVIDENCE_FOR_SUPPORTED",
        "SAFETY_FLAG_METADATA_ONLY_SUPPORTED",
        "SAFETY_FLAG_SOURCE_UNAVAILABLE",
        "SAFETY_ENABLE_GENAI_RAG_CONFLICT_CHECK",
        "SAFETY_MAX_CONFIDENCE_WITH_METADATA_ONLY",
        "SAFETY_MAX_CONFIDENCE_WITH_SOURCE_UNAVAILABLE",
        "SAFETY_MAX_CONFIDENCE_WITH_LOW_SIMILARITY",
        "SAFETY_POLICY_VERSION",
    }
    return {key: value for key in keys if (value := os.getenv(key)) is not None}


@lru_cache
def get_settings() -> Settings:
    return Settings(**_read_env())
