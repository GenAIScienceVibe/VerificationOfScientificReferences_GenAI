from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Claim, EvidencePackage, RagRetrievalResult, Reference
from app.models.enums import DoiStatus, EvidenceAvailability, RetrievalStatus
from app.repositories import RagRetrievalResultRepository
from app.services.evidence_package_builder import EvidencePackageBuilder

logger = logging.getLogger(__name__)

ALLOWED_RETRIEVAL_STATUSES = {item.value for item in RetrievalStatus}
ALLOWED_EVIDENCE_TYPES = {"ABSTRACT", "METADATA", "FULL_TEXT", "REFERENCE", "UNKNOWN", "MOCK"}

# Map backend DoiStatus values → RAG DoiStatus values (VALID / INVALID / UNRESOLVABLE)
_DOI_STATUS_TO_RAG: dict[str, str] = {
    DoiStatus.FOUND.value: "VALID",
    DoiStatus.VALID.value: "VALID",
    DoiStatus.MISSING.value: "UNRESOLVABLE",
    DoiStatus.LOOKUP_FAILED.value: "UNRESOLVABLE",
    DoiStatus.MALFORMED.value: "INVALID",
    DoiStatus.INVALID.value: "INVALID",
}

# Map backend EvidenceAvailability values → RAG EvidenceAvailability values
# PREPRINT_AVAILABLE is treated as ABSTRACT_AVAILABLE for the RAG pipeline;
# the preprint distinction is handled by the safety policy, not the retrieval layer.
_EVIDENCE_AVAIL_TO_RAG: dict[str, str] = {
    EvidenceAvailability.FULL_TEXT_AVAILABLE.value: "FULL_TEXT_AVAILABLE",
    EvidenceAvailability.ABSTRACT_AVAILABLE.value: "ABSTRACT_AVAILABLE",
    EvidenceAvailability.PREPRINT_AVAILABLE.value: "ABSTRACT_AVAILABLE",
    EvidenceAvailability.METADATA_ONLY.value: "UNAVAILABLE",
    EvidenceAvailability.SOURCE_UNAVAILABLE.value: "UNAVAILABLE",
}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _clamp_top_k(value: int | None, default: int) -> int:
    if value is None:
        return default
    return min(max(int(value), 1), 20)


@dataclass(frozen=True)
class RagClientResult:
    payload: dict[str, Any]
    mock_mode: bool


class RagResponseValidator:
    """Validates backend-to-RAG response before persistence.

    BE-9 does not trust RAG/ML output blindly and does not accept final support
    labels. The response must contain retrieval-quality information only.
    """

    def validate(self, response: dict[str, Any], *, claim_id: str, reference_id: str) -> dict[str, Any]:
        if not isinstance(response, dict):
            raise ValueError("RAG response must be a JSON object.")
        if response.get("claim_id") != claim_id:
            raise ValueError("RAG response claim_id does not match the request.")
        if response.get("reference_id") != reference_id:
            raise ValueError("RAG response reference_id does not match the request.")
        status = response.get("retrieval_status")
        if status not in ALLOWED_RETRIEVAL_STATUSES:
            raise ValueError(f"Unsupported retrieval_status: {status!r}.")
        if "support_status" in response:
            raise ValueError("BE-9 RAG responses must not return final support_status labels.")

        chunks = response.get("top_chunks", [])
        if chunks is None:
            chunks = []
        if not isinstance(chunks, list):
            raise ValueError("top_chunks must be a list.")
        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise ValueError(f"top_chunks[{index}] must be an object.")
            if not str(chunk.get("chunk_text") or "").strip():
                raise ValueError(f"top_chunks[{index}].chunk_text is required.")
            chunk["similarity_score"] = self._validate_score(chunk.get("similarity_score"), f"top_chunks[{index}].similarity_score")
            evidence_type = str(chunk.get("evidence_type") or "UNKNOWN").upper()
            chunk["evidence_type"] = evidence_type if evidence_type in ALLOWED_EVIDENCE_TYPES else "UNKNOWN"

        for field in ("overall_similarity_score", "retrieval_confidence"):
            if response.get(field) is not None:
                response[field] = self._validate_score(response.get(field), field)

        semantic = response.get("semantic_cache_match")
        if semantic is not None:
            if not isinstance(semantic, dict):
                raise ValueError("semantic_cache_match must be an object when provided.")
            if "matched" in semantic and not isinstance(semantic.get("matched"), bool):
                raise ValueError("semantic_cache_match.matched must be boolean.")
            if semantic.get("similarity") is not None:
                self._validate_score(semantic.get("similarity"), "semantic_cache_match.similarity")

        response["top_chunks"] = chunks
        return response

    def _validate_score(self, value: Any, field: str) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a number.") from exc
        if score < 0:
            raise ValueError(f"{field} must be >= 0.")
        # Clamp scores slightly above 1.0 (e.g. from floating-point section-weight
        # arithmetic in the RAG) rather than rejecting them outright.
        return min(score, 1.0)


class RagRequestBuilder:
    """Builds the stable backend-to-RAG request from a BE-7 EvidencePackage."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build(self, package: EvidencePackage, *, top_k: int | None = None) -> dict[str, Any]:
        contract = EvidencePackageBuilder(self.settings).package_to_contract(package)
        metadata = contract.get("metadata") or {}
        source_evidence = contract.get("source_evidence") or {}
        policy = contract.get("policy") or {}

        # (a) Map backend DoiStatus → RAG DoiStatus (VALID/INVALID/UNRESOLVABLE).
        raw_doi_status = contract.get("doi_status") or ""
        doi_status_for_rag = _DOI_STATUS_TO_RAG.get(raw_doi_status, "UNRESOLVABLE")

        # (b) Map backend EvidenceAvailability → RAG EvidenceAvailability
        #     (FULL_TEXT_AVAILABLE / ABSTRACT_AVAILABLE / UNAVAILABLE).
        raw_avail = source_evidence.get("evidence_availability") or EvidenceAvailability.SOURCE_UNAVAILABLE.value
        evidence_avail_for_rag = _EVIDENCE_AVAIL_TO_RAG.get(raw_avail, "UNAVAILABLE")

        # (c) RAG SourceEvidence requires non-None strings for text and source_url.
        text_for_rag = source_evidence.get("text") or ""
        source_url_for_rag = source_evidence.get("source_url") or ""

        return {
            "document_id": package.document_id,
            "claim_id": package.claim_id,
            "reference_id": package.reference_id,
            "evidence_package_id": package.id,
            "claim_text": contract.get("claim_text"),
            "citation_text": contract.get("citation_text"),
            "doi": contract.get("doi"),
            "doi_status": doi_status_for_rag,
            "metadata": metadata,
            "source_evidence": {
                "evidence_availability": evidence_avail_for_rag,
                "text": text_for_rag,
                "source_url": source_url_for_rag,
            },
            "retrieval_options": {
                "top_k": _clamp_top_k(top_k, self.settings.rag_top_k),
                "min_similarity_threshold": self.settings.rag_min_similarity_threshold,
            },
            "policy": {
                "embedding_model_version": policy.get("embedding_model_version") or self.settings.embedding_model_version,
                "prompt_version": policy.get("prompt_version") or self.settings.verification_prompt_version,
                "verification_policy_version": policy.get("verification_policy_version") or self.settings.verification_policy_version,
                "rag_request_version": self.settings.rag_request_version,
            },
        }

    def summary(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        source = request_payload.get("source_evidence") or {}
        return {
            "document_id": request_payload.get("document_id"),
            "claim_id": request_payload.get("claim_id"),
            "reference_id": request_payload.get("reference_id"),
            "evidence_package_id": request_payload.get("evidence_package_id"),
            "doi": request_payload.get("doi"),
            "evidence_availability": source.get("evidence_availability"),
            "source_text_preview": str(source.get("text") or "")[:240] if source.get("text") else None,
            "top_k": (request_payload.get("retrieval_options") or {}).get("top_k"),
            "policy": request_payload.get("policy"),
        }


class MockRagClient:
    """Local deterministic RAG stub for BE-9 validation and demos.

    This is explicitly not final RAG/ML quality. It only echoes backend-curated
    evidence text or metadata into chunk-shaped retrieval results.
    """

    def retrieve(self, request_payload: dict[str, Any]) -> RagClientResult:
        source = request_payload.get("source_evidence") or {}
        metadata = request_payload.get("metadata") or {}
        availability = source.get("evidence_availability") or EvidenceAvailability.SOURCE_UNAVAILABLE.value
        text = str(source.get("text") or "").strip()
        source_name = "mock_rag"
        evidence_type = "UNKNOWN"
        if availability == EvidenceAvailability.ABSTRACT_AVAILABLE.value and text:
            evidence_type = "ABSTRACT"
            source_name = "metadata_abstract"
        elif availability == EvidenceAvailability.PREPRINT_AVAILABLE.value and text:
            evidence_type = "ABSTRACT"
            source_name = "preprint_abstract"
        elif availability == EvidenceAvailability.FULL_TEXT_AVAILABLE.value and text:
            evidence_type = "FULL_TEXT"
            source_name = "backend_full_text"
        elif availability == EvidenceAvailability.METADATA_ONLY.value:
            title = metadata.get("title") or ""
            authors = metadata.get("authors") or []
            if isinstance(authors, list):
                authors_text = ", ".join(str(item) for item in authors if item)
            else:
                authors_text = str(authors or "")
            bits = [str(item).strip() for item in [title, authors_text, metadata.get("year"), metadata.get("venue")] if str(item or "").strip()]
            text = ". ".join(bits)
            evidence_type = "METADATA"
            source_name = "metadata_fields"

        if not text:
            return RagClientResult(
                payload={
                    "claim_id": request_payload.get("claim_id"),
                    "reference_id": request_payload.get("reference_id"),
                    "retrieval_status": RetrievalStatus.NO_RELEVANT_EVIDENCE_FOUND.value,
                    "top_chunks": [],
                    "overall_similarity_score": 0.0,
                    "retrieval_confidence": 0.0,
                    "semantic_cache_match": {"matched": False, "cached_result_id": None, "similarity": None},
                },
                mock_mode=True,
            )

        top_k = int((request_payload.get("retrieval_options") or {}).get("top_k") or 1)
        preview = " ".join(text.split())[:1500]
        chunks = [
            {
                "chunk_id": "mock_chunk_001",
                "chunk_text": preview,
                "similarity_score": 0.76 if evidence_type == "METADATA" else 0.82,
                "evidence_type": evidence_type,
                "source": source_name,
                "source_url": source.get("source_url") or metadata.get("url"),
            }
        ][:top_k]
        return RagClientResult(
            payload={
                "claim_id": request_payload.get("claim_id"),
                "reference_id": request_payload.get("reference_id"),
                "retrieval_status": RetrievalStatus.SUCCEEDED.value,
                "top_chunks": chunks,
                "overall_similarity_score": chunks[0]["similarity_score"],
                "retrieval_confidence": max(0.0, chunks[0]["similarity_score"] - 0.03),
                "semantic_cache_match": {"matched": False, "cached_result_id": None, "similarity": None},
            },
            mock_mode=True,
        )


class RagDirectClient:
    """Calls rag/api.retrieve_evidence() directly as a Python import — no HTTP, no mock."""

    def __init__(self) -> None:
        import pathlib
        import sys
        # rag/ lives at the project root, one level above backend/
        project_root = str(pathlib.Path(__file__).resolve().parent.parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def retrieve(self, request_payload: dict[str, Any]) -> RagClientResult:
        from rag.api import RetrieveEvidenceRequest, retrieve_evidence  # noqa: PLC0415
        from rag.ingestion.models import SourceEvidence  # noqa: PLC0415

        source_ev = request_payload.get("source_evidence") or {}
        req = RetrieveEvidenceRequest(
            claim_id=request_payload["claim_id"],
            reference_id=request_payload["reference_id"],
            claim_text=request_payload["claim_text"],
            citation_text=request_payload.get("citation_text") or "",
            doi=request_payload.get("doi") or "",
            doi_status=request_payload["doi_status"],
            source_evidence=SourceEvidence(
                evidence_availability=source_ev.get("evidence_availability", "UNAVAILABLE"),
                text=source_ev.get("text") or "",
                source_url=source_ev.get("source_url") or "",
            ),
        )
        response = retrieve_evidence(req)
        payload: dict[str, Any] = {
            "claim_id": response.claim_id,
            "reference_id": response.reference_id,
            "retrieval_status": response.retrieval_status.value,
            "top_chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "chunk_text": c.chunk_text,
                    "similarity_score": c.similarity_score,
                    "evidence_type": c.evidence_type,
                }
                for c in response.top_chunks
            ],
            "overall_similarity_score": response.overall_similarity_score,
            "retrieval_confidence": response.retrieval_confidence,
        }
        return RagClientResult(payload=payload, mock_mode=False)


class RagMlClient:
    """Coordinator that routes RAG retrieval to the real pipeline or the mock stub."""

    def __init__(
        self,
        settings: Settings | None = None,
        mock_client: MockRagClient | None = None,
        direct_client: RagDirectClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.mock_client = mock_client or MockRagClient()
        self.direct_client = direct_client or RagDirectClient()

    def retrieve(self, request_payload: dict[str, Any], *, use_mock: bool | None = None) -> RagClientResult:
        if use_mock is True or self.settings.rag_mock_mode or not self.settings.rag_service_enabled:
            return self.mock_client.retrieve(request_payload)
        return self.direct_client.retrieve(request_payload)

    def _http_retrieve_unused(self, request_payload: dict[str, Any]) -> RagClientResult:
        """Retained for reference — the real pipeline is now called directly via RagDirectClient."""
        if not self.settings.rag_service_url:
            raise AppException(status_code=503, code=ErrorCode.RAG_SERVICE_UNAVAILABLE, detail="RAG service URL is not configured.", message="RAG service unavailable")
        url = self.settings.rag_service_url.rstrip("/") + "/internal/rag/retrieve-evidence"
        attempts = max(1, self.settings.rag_service_max_retries + 1)
        last_error: Exception | None = None
        for _attempt in range(attempts):
            try:
                with httpx.Client(timeout=self.settings.rag_service_timeout_seconds) as client:
                    response = client.post(url, json=request_payload)
                    response.raise_for_status()
                    return RagClientResult(payload=response.json(), mock_mode=False)
            except httpx.TimeoutException as exc:
                last_error = exc
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in {429, 500, 502, 503, 504}:
                    last_error = exc
                    continue
                raise AppException(status_code=502, code=ErrorCode.RAG_RETRIEVAL_FAILED, detail=f"RAG service returned HTTP {status}.", message="RAG retrieval failed") from exc
            except httpx.RequestError as exc:
                last_error = exc
                continue
            except ValueError as exc:
                raise AppException(status_code=502, code=ErrorCode.RAG_INVALID_RESPONSE, detail="RAG service returned invalid JSON.", message="Invalid RAG response") from exc
        if isinstance(last_error, httpx.TimeoutException):
            raise AppException(status_code=504, code=ErrorCode.RAG_SERVICE_TIMEOUT, detail="RAG evidence retrieval timed out.", message="RAG service timeout") from last_error
        raise AppException(status_code=503, code=ErrorCode.RAG_SERVICE_UNAVAILABLE, detail="RAG service is unavailable.", message="RAG service unavailable") from last_error


class RagRetrievalService:
    """BE-9 coordinator: request build, RAG call, response validation, persistence."""

    def __init__(
        self,
        settings: Settings | None = None,
        rag_client: RagMlClient | None = None,
        validator: RagResponseValidator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.request_builder = RagRequestBuilder(self.settings)
        self.rag_client = rag_client or RagMlClient(self.settings)
        self.validator = validator or RagResponseValidator()

    def retrieve_evidence_for_claim(
        self,
        claim_id: str,
        db: Session,
        *,
        reference_id: str | None = None,
        evidence_package_id: str | None = None,
        top_k: int | None = None,
        force_refresh: bool = False,
        use_mock: bool | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail=f"Claim '{claim_id}' was not found.", message="Claim not found")
        package = self._resolve_evidence_package(claim, db, reference_id=reference_id, evidence_package_id=evidence_package_id)
        # (f) METADATA_ONLY and SOURCE_UNAVAILABLE skip Door 1 (retrieve_evidence).
        #     The orchestrator routes them directly to Door 2 (GenAI verification).
        _skip_availabilities = {
            EvidenceAvailability.SOURCE_UNAVAILABLE.value,
            EvidenceAvailability.METADATA_ONLY.value,
        }
        if package.evidence_availability in _skip_availabilities:
            reason = "source_unavailable" if package.evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value else "metadata_only"
            logger.info(
                "rag_retrieval_skipped_%s" % reason,
                extra={"request_id": request_id, "claim_id": claim_id, "evidence_package_id": package.id},
            )
            result = self._store_result(
                db,
                package=package,
                retrieval_status=RetrievalStatus.NO_RELEVANT_EVIDENCE_FOUND.value,
                top_chunks=[],
                overall_similarity_score=0.0,
                retrieval_confidence=0.0,
                semantic_cache_match=None,
                request_summary={"reason": reason, "evidence_package_id": package.id},
                response_payload=None,
                error_message=f"Evidence package has {package.evidence_availability}; Door 1 was skipped by BE-9 policy.",
            )
            db.commit()
            db.refresh(result)
            return self.result_to_dict(result)

        request_payload = self.request_builder.build(package, top_k=top_k)
        logger.info(
            "rag_retrieval_start",
            extra={"request_id": request_id, "claim_id": claim_id, "reference_id": package.reference_id, "evidence_package_id": package.id, "force_refresh": force_refresh},
        )
        try:
            client_result = self.rag_client.retrieve(request_payload, use_mock=use_mock)
            validated = self.validator.validate(client_result.payload, claim_id=claim.id, reference_id=package.reference_id)
        except AppException as exc:
            self._store_failure_for_exception(db, package=package, request_payload=request_payload, exc=exc)
            db.commit()
            raise
        except ValueError as exc:
            self._store_result(
                db,
                package=package,
                retrieval_status=RetrievalStatus.FAILED.value,
                top_chunks=[],
                overall_similarity_score=None,
                retrieval_confidence=None,
                semantic_cache_match=None,
                request_summary=self.request_builder.summary(request_payload),
                response_payload=None,
                error_message=str(exc),
            )
            db.commit()
            raise AppException(status_code=502, code=ErrorCode.RAG_INVALID_RESPONSE, field="claim_id", detail=str(exc), message="Invalid RAG response") from exc

        result = self._store_result(
            db,
            package=package,
            retrieval_status=validated.get("retrieval_status"),
            top_chunks=validated.get("top_chunks") or [],
            overall_similarity_score=validated.get("overall_similarity_score"),
            retrieval_confidence=validated.get("retrieval_confidence"),
            semantic_cache_match=validated.get("semantic_cache_match"),
            request_summary=self.request_builder.summary(request_payload),
            response_payload={**validated, "mock_mode": client_result.mock_mode},
            error_message=None,
        )
        db.commit()
        db.refresh(result)
        logger.info(
            "rag_retrieval_completed",
            extra={"request_id": request_id, "retrieval_result_id": result.id, "claim_id": claim_id, "status": result.retrieval_status, "chunks_count": len(result.top_chunks_json or [])},
        )
        return self.result_to_dict(result)

    def list_claim_retrieval_results(
        self,
        claim_id: str,
        db: Session,
        *,
        reference_id: str | None = None,
        latest_only: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail=f"Claim '{claim_id}' was not found.", message="Claim not found")
        total, results = RagRetrievalResultRepository(db).list_for_claim(claim_id, reference_id=reference_id, latest_only=latest_only, page=page, page_size=page_size)
        return {"claim_id": claim_id, "total": total, "page": page, "page_size": page_size, "latest_only": latest_only, "retrieval_results": [self.result_to_dict(item) for item in results]}

    def _resolve_evidence_package(
        self,
        claim: Claim,
        db: Session,
        *,
        reference_id: str | None = None,
        evidence_package_id: str | None = None,
    ) -> EvidencePackage:
        statement = select(EvidencePackage).options(
            selectinload(EvidencePackage.claim),
            selectinload(EvidencePackage.reference),
            selectinload(EvidencePackage.citation),
            selectinload(EvidencePackage.claim_reference_link),
        )
        if evidence_package_id:
            package = db.scalar(statement.where(EvidencePackage.id == evidence_package_id))
            if package is None or package.claim_id != claim.id:
                raise AppException(status_code=404, code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND, field="evidence_package_id", detail="Evidence package was not found for this claim.", message="Evidence package not found")
            if reference_id and package.reference_id != reference_id:
                raise AppException(status_code=400, code=ErrorCode.VALIDATION_ERROR, field="reference_id", detail="reference_id does not match the selected evidence_package_id.", message="Validation failed")
            return package
        query = statement.where(EvidencePackage.claim_id == claim.id)
        if reference_id:
            reference = db.get(Reference, reference_id)
            if reference is None or reference.document_id != claim.document_id:
                raise AppException(status_code=404, code=ErrorCode.REFERENCE_NOT_FOUND, field="reference_id", detail="Reference was not found for this claim/document.", message="Reference not found")
            query = query.where(EvidencePackage.reference_id == reference_id)
        package = db.scalar(query.order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc()).limit(1))
        if package is None:
            raise AppException(status_code=404, code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND, field="claim_id", detail="No evidence package exists for this claim. Run /prepare-evidence first.", message="Evidence package not found")
        return package

    def _store_failure_for_exception(self, db: Session, *, package: EvidencePackage, request_payload: dict[str, Any], exc: AppException) -> None:
        status = RetrievalStatus.FAILED.value
        if exc.error.code == ErrorCode.RAG_SERVICE_TIMEOUT.value:
            status = RetrievalStatus.TIMEOUT.value
        elif exc.error.code == ErrorCode.RAG_SERVICE_UNAVAILABLE.value:
            status = RetrievalStatus.SERVICE_UNAVAILABLE.value
        self._store_result(
            db,
            package=package,
            retrieval_status=status,
            top_chunks=[],
            overall_similarity_score=None,
            retrieval_confidence=None,
            semantic_cache_match=None,
            request_summary=self.request_builder.summary(request_payload),
            response_payload=None,
            error_message=exc.error.detail,
        )

    def _store_result(
        self,
        db: Session,
        *,
        package: EvidencePackage,
        retrieval_status: str,
        top_chunks: list[dict[str, Any]],
        overall_similarity_score: float | None,
        retrieval_confidence: float | None,
        semantic_cache_match: dict[str, Any] | None,
        request_summary: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        error_message: str | None,
    ) -> RagRetrievalResult:
        result = RagRetrievalResult(
            document_id=package.document_id,
            claim_id=package.claim_id,
            reference_id=package.reference_id,
            evidence_package_id=package.id,
            retrieval_status=retrieval_status,
            top_chunks_json=top_chunks,
            overall_similarity_score=overall_similarity_score,
            retrieval_confidence=retrieval_confidence,
            semantic_cache_match_json=semantic_cache_match,
            request_payload_summary=request_summary,
            response_payload_json=response_payload,
            error_message=error_message,
        )
        db.add(result)
        db.flush()
        return result

    def result_to_dict(self, result: RagRetrievalResult) -> dict[str, Any]:
        return {
            "retrieval_result_id": result.id,
            "document_id": result.document_id,
            "claim_id": result.claim_id,
            "reference_id": result.reference_id,
            "evidence_package_id": result.evidence_package_id,
            "retrieval_status": result.retrieval_status,
            "top_chunks": result.top_chunks_json or [],
            "overall_similarity_score": result.overall_similarity_score,
            "retrieval_confidence": result.retrieval_confidence,
            "semantic_cache_match": result.semantic_cache_match_json,
            "request_payload_summary": result.request_payload_summary,
            "error_message": result.error_message,
            "created_at": _iso(result.created_at),
            "updated_at": _iso(result.updated_at),
            "phase": "BE-9",
            "processing_note": "BE-9 performs backend-controlled RAG/ML retrieval integration only. It does not verify support status or call GenAI verification.",
        }
