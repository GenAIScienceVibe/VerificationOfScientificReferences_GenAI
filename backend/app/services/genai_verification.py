from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.models.enums import SupportStatus

logger = logging.getLogger(__name__)

ALLOWED_SUPPORT_STATUSES = {item.value for item in SupportStatus}


@dataclass(frozen=True)
class GenAiVerificationClientResult:
    payload: dict[str, Any]
    raw_output: Any
    mock_mode: bool
    token_usage: dict[str, Any] | None = None


class GenAiVerificationResponseValidator:
    """Validates GenAI verification output before BE-10 stores it."""

    def validate(self, response: dict[str, Any] | str, *, retrieved_chunks: list[dict[str, Any]]) -> dict[str, Any]:
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError as exc:
                raise ValueError("GenAI verification response must be valid JSON.") from exc
        if not isinstance(response, dict):
            raise ValueError("GenAI verification response must be a JSON object.")

        status = response.get("support_status")
        if status not in ALLOWED_SUPPORT_STATUSES:
            raise ValueError(f"Unsupported support_status: {status!r}.")
        try:
            confidence = float(response.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be a number between 0 and 1.") from exc
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1.")
        explanation = str(response.get("explanation") or "").strip()
        if not explanation:
            raise ValueError("explanation is required.")
        evidence_used = response.get("evidence_used") or []
        if not isinstance(evidence_used, list):
            raise ValueError("evidence_used must be a list.")
        available_chunk_ids = {str(chunk.get("chunk_id")) for chunk in retrieved_chunks if chunk.get("chunk_id")}
        for chunk_id in evidence_used:
            if str(chunk_id) not in available_chunk_ids:
                raise ValueError(f"evidence_used contains unknown chunk_id: {chunk_id!r}.")
        if not isinstance(response.get("human_review_required"), bool):
            raise ValueError("human_review_required must be boolean.")

        return {
            "support_status": status,
            "confidence": confidence,
            "explanation": explanation,
            "evidence_used": [str(item) for item in evidence_used],
            "limitations": str(response.get("limitations") or "No additional limitations were provided."),
            "human_review_required": bool(response.get("human_review_required")),
        }


class MockGenAiVerificationClient:
    """Deterministic local GenAI-verification stand-in for tests/demos.

    This intentionally does not claim final AI quality. It lets BE-10 validate
    orchestration, response validation, result persistence, and safety gates
    without a live Groq call.
    """

    def verify_claim(self, request_payload: dict[str, Any]) -> GenAiVerificationClientResult:
        chunks = request_payload.get("retrieved_evidence") or []
        overall_similarity = float(request_payload.get("overall_similarity_score") or 0.0)
        doi_status = str(request_payload.get("doi_status") or "").upper()
        if doi_status in {"MISSING", "MALFORMED", "INVALID"}:
            payload = {
                "support_status": SupportStatus.NEEDS_HUMAN_REVIEW.value,
                "confidence": 0.25,
                "explanation": "The DOI is missing, malformed, or invalid, so automated support verification is unsafe.",
                "evidence_used": [],
                "limitations": "A valid DOI is required before automated verification can be trusted.",
                "human_review_required": True,
            }
        elif not chunks:
            payload = {
                "support_status": SupportStatus.INSUFFICIENT_EVIDENCE.value,
                "confidence": 0.30,
                "explanation": "No retrieved evidence chunks were available for the claim.",
                "evidence_used": [],
                "limitations": "The backend had no evidence chunks to compare against the claim.",
                "human_review_required": True,
            }
        else:
            first_chunk_id = str(chunks[0].get("chunk_id"))
            if overall_similarity >= 0.80:
                status = SupportStatus.PARTIALLY_SUPPORTED.value
                confidence = 0.72
                review = False
                explanation = "The retrieved evidence is related to the claim, but BE-10 mock verification treats it as partial support only."
            elif overall_similarity >= 0.60:
                status = SupportStatus.INSUFFICIENT_EVIDENCE.value
                confidence = 0.55
                review = True
                explanation = "The retrieved evidence has only moderate similarity, so the claim requires careful review."
            else:
                status = SupportStatus.NEEDS_HUMAN_REVIEW.value
                confidence = 0.40
                review = True
                explanation = "The retrieved evidence similarity is too low for a confident automated result."
            payload = {
                "support_status": status,
                "confidence": confidence,
                "explanation": explanation,
                "evidence_used": [first_chunk_id],
                "limitations": "Mock GenAI mode validates BE-10 orchestration only; final judgment requires a real configured GenAI service and BE-11 safety rules.",
                "human_review_required": review,
            }
        return GenAiVerificationClientResult(payload=payload, raw_output=payload, mock_mode=True, token_usage=None)


class RealGenAiVerificationClient:
    """Calls rag/api.verify_claim() directly — real LLM via OpenRouter, no mock."""

    # Maps backend DoiStatus values to the three values rag/api.py accepts.
    _DOI_MAP: dict[str, str] = {
        "FOUND": "VALID", "VALID": "VALID",
        "MISSING": "UNRESOLVABLE", "LOOKUP_FAILED": "UNRESOLVABLE",
        "MALFORMED": "INVALID", "INVALID": "INVALID",
    }

    def __init__(self) -> None:
        import pathlib
        import sys
        project_root = str(pathlib.Path(__file__).resolve().parent.parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def verify_claim(self, request_payload: dict[str, Any]) -> GenAiVerificationClientResult:
        from rag.api import (  # noqa: PLC0415
            RetrievedEvidenceItem,
            SourceMetadata,
            VerifyClaimRequest,
            verify_claim,
        )

        doi_status = self._DOI_MAP.get(str(request_payload.get("doi_status") or ""), "UNRESOLVABLE")
        metadata = request_payload.get("metadata") or {}
        retrieved = request_payload.get("retrieved_evidence") or []

        req = VerifyClaimRequest(
            claim_text=request_payload.get("claim_text") or "",
            citation_text=request_payload.get("citation_text") or "",
            doi_status=doi_status,
            metadata=SourceMetadata(
                title=str(metadata.get("title") or ""),
                abstract=str(metadata.get("abstract") or ""),
            ),
            retrieved_evidence=[
                RetrievedEvidenceItem(
                    chunk_id=str(c.get("chunk_id") or i),
                    chunk_text=str(c.get("chunk_text") or ""),
                    similarity_score=float(c.get("similarity_score") or 0.0),
                )
                for i, c in enumerate(retrieved)
            ],
            overall_similarity_score=float(request_payload.get("overall_similarity_score") or 0.0),
        )
        response = verify_claim(req)
        payload: dict[str, Any] = {
            "support_status": response.support_status.value,
            "confidence": response.confidence,
            "explanation": response.explanation,
            "evidence_used": response.evidence_used,
            "limitations": response.limitations or "No additional limitations were provided.",
            "human_review_required": response.human_review_required,
        }
        return GenAiVerificationClientResult(payload=payload, raw_output=response, mock_mode=False)


class GenAiVerificationService:
    """Backend-controlled GenAI verification façade.

    Uses RealGenAiVerificationClient when GENAI_MOCK_MODE=false (calls rag/api.verify_claim()
    directly via OpenRouter). Falls back to MockGenAiVerificationClient when mock mode is on.
    """

    def __init__(self, settings: Settings | None = None, client: MockGenAiVerificationClient | None = None) -> None:
        self.settings = settings or get_settings()
        if client is not None:
            self.client = client
        elif self.settings.genai_mock_mode:
            self.client = MockGenAiVerificationClient()
        else:
            self.client = RealGenAiVerificationClient()
        self.validator = GenAiVerificationResponseValidator()

    def build_request(
        self,
        *,
        claim_id: str,
        claim_text: str,
        citation_text: str | None,
        doi_status: str,
        metadata: dict[str, Any] | None,
        retrieved_evidence: list[dict[str, Any]],
        overall_similarity_score: float | None,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim_id,
            "claim_text": claim_text,
            "citation_text": citation_text,
            "doi_status": doi_status,
            "metadata": metadata or {},
            "retrieved_evidence": retrieved_evidence,
            "overall_similarity_score": overall_similarity_score,
            "instructions": {
                "allowed_support_statuses": sorted(ALLOWED_SUPPORT_STATUSES),
                "source_of_truth": "Use only the provided claim, metadata, and retrieved evidence. Do not use outside knowledge or invent evidence.",
                "output_format": "valid JSON only",
            },
        }

    def verify(self, request_payload: dict[str, Any]) -> tuple[dict[str, Any], GenAiVerificationClientResult]:
        result = self.client.verify_claim(request_payload)
        validated = self.validator.validate(result.payload, retrieved_chunks=request_payload.get("retrieved_evidence") or [])
        return validated, result
