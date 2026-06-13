from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models.enums import ClaimType
from app.services.claim_preparation import PreparedSentence

ALLOWED_CLAIM_TYPES = {item.value for item in ClaimType}


@dataclass(frozen=True)
class ExtractedClaimCandidate:
    claim_text: str
    citation_text: str
    claim_type: str
    confidence: float


class ClaimExtractionValidator:
    """Validates model JSON before BE-6 writes claims to the database."""

    def validate(self, output: str | dict[str, Any], prepared_sentence: PreparedSentence) -> list[ExtractedClaimCandidate]:
        try:
            payload = json.loads(output) if isinstance(output, str) else output
        except json.JSONDecodeError as exc:
            raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="genai_response", detail="GenAI returned invalid JSON.", message="Invalid GenAI JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
            raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="genai_response", detail="GenAI response must contain a claims array.", message="Invalid GenAI JSON")

        detected = {item.citation_text for item in prepared_sentence.detected_citations}
        valid: list[ExtractedClaimCandidate] = []
        for item in payload["claims"]:
            if not isinstance(item, dict):
                continue
            claim_text = str(item.get("claim_text") or "").strip()
            citation_text = str(item.get("citation_text") or "").strip()
            claim_type = str(item.get("claim_type") or ClaimType.UNKNOWN.value).strip().upper()
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = -1.0
            if not claim_text:
                raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="claim_text", detail="GenAI claim is missing claim_text.", message="Invalid GenAI output")
            if not citation_text or (citation_text not in detected and citation_text not in prepared_sentence.sentence_text):
                raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="citation_text", detail="GenAI claim citation_text was not found in the source sentence.", message="Invalid GenAI output")
            if claim_type not in ALLOWED_CLAIM_TYPES:
                raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="claim_type", detail="GenAI returned an unsupported claim_type.", message="Invalid GenAI output")
            if confidence < 0 or confidence > 1:
                raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="confidence", detail="GenAI confidence must be between 0 and 1.", message="Invalid GenAI output")
            if not self._is_grounded(claim_text, prepared_sentence.sentence_text):
                raise AppException(status_code=502, code=ErrorCode.GENAI_INVALID_JSON, field="claim_text", detail="GenAI claim_text is not grounded in the provided paragraph/sentence.", message="Invalid GenAI output")
            valid.append(ExtractedClaimCandidate(claim_text=claim_text, citation_text=citation_text, claim_type=claim_type, confidence=confidence))
        return valid

    def _is_grounded(self, claim_text: str, sentence_text: str) -> bool:
        claim_tokens = {token.lower() for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", claim_text)}
        sentence_tokens = {token.lower() for token in re.findall(r"[A-Za-zÀ-ÿ]{4,}", sentence_text)}
        if not claim_tokens:
            return False
        return len(claim_tokens & sentence_tokens) / max(len(claim_tokens), 1) >= 0.45


class LocalDeterministicClaimExtractionClient:
    """Mockable backend-controlled claim extraction client.

    In local/demo mode this deterministic client simulates the internal GenAI contract
    without calling Groq. It extracts only citation-linked sentence claims and keeps
    the same JSON shape expected from a real backend-controlled GenAI client.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.validator = ClaimExtractionValidator()

    @property
    def model_provider(self) -> str:
        return self.settings.genai_provider

    @property
    def model_name(self) -> str:
        return self.settings.groq_model

    @property
    def prompt_version(self) -> str:
        return self.settings.claim_extraction_prompt_version

    def extract_claims(self, *, document_id: str, prepared_sentence: PreparedSentence) -> tuple[list[ExtractedClaimCandidate], dict[str, Any]]:
        claims = []
        for citation in prepared_sentence.detected_citations:
            claim_text = self._sentence_to_claim(prepared_sentence.sentence_text, [item.citation_text for item in prepared_sentence.detected_citations])
            if len(claim_text) < 20:
                continue
            claims.append(
                {
                    "claim_text": claim_text,
                    "citation_text": citation.citation_text,
                    "claim_type": self._guess_claim_type(claim_text),
                    "confidence": 0.78,
                }
            )
        output = {"claims": claims}
        return self.validator.validate(output, prepared_sentence), output

    def _sentence_to_claim(self, sentence: str, citation_texts: list[str]) -> str:
        claim = sentence
        for citation_text in citation_texts:
            claim = claim.replace(citation_text, " ")
        claim = re.sub(r"\s+", " ", claim).strip(" .;,")
        # Remove narrative author-year citation year while keeping the actual statement readable.
        claim = re.sub(r"\b([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+(?:\s+et\s+al\.|\s+(?:and|&)\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)?)\s*\((?:19|20)\d{2}[a-z]?\)", r"\1", claim)
        return claim.rstrip(".") + "."

    def _guess_claim_type(self, claim_text: str) -> str:
        lowered = claim_text.lower()
        if any(word in lowered for word in ("causes", "causal", "impact", "influence", "affect", "effect")):
            return ClaimType.CAUSAL.value
        if any(word in lowered for word in ("method", "sample", "survey", "analysis", "model", "design")):
            return ClaimType.METHODOLOGICAL.value
        if any(word in lowered for word in ("compared", "more than", "less than", "higher", "lower")):
            return ClaimType.COMPARATIVE.value
        if any(word in lowered for word in ("defines", "refers to", "is defined")):
            return ClaimType.DEFINITION.value
        if any(word in lowered for word in ("framework", "theory", "conceptual", "posits")):
            return ClaimType.THEORETICAL.value
        if any(word in lowered for word in ("found", "show", "demonstrat", "reported", "revealed", "suggest")):
            return ClaimType.EMPIRICAL.value
        return ClaimType.BACKGROUND.value
