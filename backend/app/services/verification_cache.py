from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import Claim, ClaimCacheIndex, ClaimReferenceLink, EvidencePackage, Reference, VerificationResult
from app.models.enums import CacheSource, SupportStatus
from app.repositories.claim_cache import ClaimCacheRepository

logger = logging.getLogger(__name__)


class CacheRecommendedAction:
    REUSE_VERIFICATION = "REUSE_VERIFICATION"
    RUN_NEW_VERIFICATION = "RUN_NEW_VERIFICATION"
    RERUN_VERIFICATION = "RERUN_VERIFICATION"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    CACHE_DISABLED = "CACHE_DISABLED"


@dataclass(frozen=True)
class CacheKey:
    normalized_claim_text: str
    normalized_claim_hash: str
    normalized_doi: str | None


def normalize_claim_text(text: str | None) -> str:
    """Normalize a claim while preserving meaning-critical content.

    The normalization is intentionally conservative: it lowercases text,
    collapses whitespace, removes harmless punctuation separators, but keeps
    negation words, numbers, units, years, p-values, and statistical symbols.
    """

    if not text:
        return ""
    value = text.lower().strip()
    value = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    # Remove punctuation that usually does not change scientific meaning. Keep
    # digits, percent signs, decimal points inside numbers, inequality signs,
    # slashes, hyphens, and common statistical notation.
    value = re.sub(r"[\"'`“”‘’]", "", value)
    value = re.sub(r"(?<!\d)[.,;:!?](?!\d)", " ", value)
    value = re.sub(r"[()\[\]{}]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def claim_hash(normalized_claim_text: str) -> str:
    return hashlib.sha256(normalized_claim_text.encode("utf-8")).hexdigest()


def normalize_doi_for_cache(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().strip("<>")
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*[: ]\s*)", "", doi, flags=re.IGNORECASE).strip()
    doi = doi.rstrip(",;")
    doi = doi.rstrip(".")
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]
    doi = doi.strip().lower()
    return doi or None


def build_cache_key(claim_text: str | None, doi: str | None) -> CacheKey:
    normalized = normalize_claim_text(claim_text)
    return CacheKey(
        normalized_claim_text=normalized,
        normalized_claim_hash=claim_hash(normalized),
        normalized_doi=normalize_doi_for_cache(doi),
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _cache_age_days(cache: ClaimCacheIndex) -> int | None:
    created = cache.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return int((datetime.now(UTC) - created).days)


class SemanticCacheClient:
    """Mockable semantic cache interface for future BE-9/RAG integration.

    BE-8 does not create embeddings, vector-search, or call RAG. This local
    implementation only compares existing cache-row normalized text using a
    lightweight token/sequence heuristic when explicitly enabled for tests.
    """

    def find_matches(self, *, claim_text: str, doi: str, candidates: list[ClaimCacheIndex], top_k: int = 5) -> list[dict[str, Any]]:
        source_tokens = set(claim_text.split())
        matches: list[dict[str, Any]] = []
        for cache in candidates:
            target = cache.normalized_claim_text or ""
            target_tokens = set(target.split())
            token_score = len(source_tokens & target_tokens) / max(len(source_tokens | target_tokens), 1)
            sequence_score = SequenceMatcher(None, claim_text, target).ratio()
            score = round(max(token_score, sequence_score), 4)
            matches.append(
                {
                    "cache_id": cache.id,
                    "verification_result_id": cache.verification_result_id,
                    "similarity_score": score,
                    "matched_claim_text": target,
                    "cache_entry": cache,
                }
            )
        return sorted(matches, key=lambda item: item["similarity_score"], reverse=True)[:top_k]


class VerificationCacheService:
    """BE-8 backend-controlled verification cache layer."""

    def __init__(self, *, settings: Settings | None = None, semantic_client: SemanticCacheClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.semantic_client = semantic_client or SemanticCacheClient()

    def check_claim_cache(
        self,
        claim_id: str,
        db: Session,
        *,
        reference_id: str | None = None,
        use_semantic_cache: bool | None = None,
        force_refresh: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        claim = db.get(Claim, claim_id)
        if claim is None:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail=f"Claim '{claim_id}' was not found.", message="Claim not found")

        reference, evidence_package = self._resolve_reference_for_claim(claim, db, reference_id=reference_id)
        doi = self._resolve_doi(reference, evidence_package)
        key = build_cache_key(claim.claim_text, doi)

        logger.info(
            "cache_lookup_start",
            extra={"request_id": request_id, "claim_id": claim_id, "reference_id": reference.id if reference else None, "doi": key.normalized_doi, "claim_hash": key.normalized_claim_hash},
        )

        if not self.settings.cache_enabled:
            return self._decision(
                claim=claim,
                reference=reference,
                key=key,
                cache_hit=False,
                cache_source=CacheSource.NEW_VERIFICATION.value,
                recommended_action=CacheRecommendedAction.CACHE_DISABLED,
                reason="Verification cache is disabled by configuration.",
            )

        if force_refresh:
            return self._decision(
                claim=claim,
                reference=reference,
                key=key,
                cache_hit=False,
                cache_source=CacheSource.NEW_VERIFICATION.value,
                recommended_action=CacheRecommendedAction.RERUN_VERIFICATION,
                reason="Force refresh requested; cache lookup bypassed.",
            )

        if not key.normalized_doi:
            return self._decision(
                claim=claim,
                reference=reference,
                key=key,
                cache_hit=False,
                cache_source=CacheSource.NEW_VERIFICATION.value,
                recommended_action=CacheRecommendedAction.NEEDS_HUMAN_REVIEW,
                reason="No DOI is available; verification cache reuse is blocked.",
            )

        if self.settings.cache_exact_enabled:
            exact = self._find_exact_cache(reference, key, db)
            if exact:
                decision = self._decision_from_cache(claim, reference, key, exact, similarity_score=1.0, exact=True)
                logger.info("exact_cache_decision", extra={"claim_id": claim_id, "cache_id": exact.id, "decision": decision["recommended_action"]})
                return decision

        semantic_enabled = bool(use_semantic_cache) and self.settings.cache_semantic_enabled
        if semantic_enabled:
            semantic = self._find_semantic_cache(reference, key, db)
            if semantic is not None:
                return semantic
        else:
            logger.info("semantic_cache_skipped", extra={"claim_id": claim_id, "reason": "disabled_or_not_requested"})

        return self._decision(
            claim=claim,
            reference=reference,
            key=key,
            cache_hit=False,
            cache_source=CacheSource.NEW_VERIFICATION.value,
            recommended_action=CacheRecommendedAction.RUN_NEW_VERIFICATION,
            reason="No reusable verification cache entry was found for the normalized claim and DOI.",
        )

    def get_claim_cache_result(self, claim_id: str, db: Session, *, request_id: str | None = None) -> dict[str, Any]:
        return self.check_claim_cache(claim_id, db, use_semantic_cache=False, request_id=request_id)

    def index_verification_result(
        self,
        verification_result_id: str,
        db: Session,
        *,
        cache_source: str = CacheSource.NEW_VERIFICATION.value,
        evidence_version: str | None = None,
        commit: bool = True,
    ) -> ClaimCacheIndex:
        result = db.get(VerificationResult, verification_result_id)
        if result is None:
            raise AppException(status_code=404, code=ErrorCode.VERIFICATION_RESULT_NOT_FOUND, field="verification_result_id", detail="Verification result was not found.", message="Verification result not found")
        claim = db.get(Claim, result.claim_id)
        reference = db.get(Reference, result.reference_id)
        if claim is None:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_NOT_FOUND, field="claim_id", detail="Claim linked to verification result was not found.", message="Claim not found")
        if reference is None:
            raise AppException(status_code=404, code=ErrorCode.REFERENCE_NOT_FOUND, field="reference_id", detail="Reference linked to verification result was not found.", message="Reference not found")
        key = build_cache_key(claim.claim_text, reference.extracted_doi)
        if not key.normalized_doi:
            raise AppException(status_code=422, code=ErrorCode.DOI_MISSING, field="verification_result_id", detail="Verification result reference does not have a DOI; cache index cannot be created.", message="DOI missing")

        evidence_version = evidence_version or self.settings.cache_evidence_version
        repo = ClaimCacheRepository(db)
        existing = repo.find_existing_key(
            normalized_claim_hash=key.normalized_claim_hash,
            doi=key.normalized_doi,
            reference_id=reference.id,
            evidence_version=evidence_version,
            embedding_model_version=self.settings.embedding_model_version,
            prompt_version=self.settings.verification_prompt_version,
            verification_policy_version=self.settings.verification_policy_version,
        )
        if existing:
            existing.normalized_claim_text = key.normalized_claim_text
            existing.verification_result_id = result.id
            existing.support_status = result.support_status
            existing.confidence = result.confidence
            existing.cache_source = cache_source
            if commit:
                db.commit()
                db.refresh(existing)
            return existing

        cache = ClaimCacheIndex(
            normalized_claim_hash=key.normalized_claim_hash,
            normalized_claim_text=key.normalized_claim_text,
            claim_embedding_id=None,
            doi=key.normalized_doi,
            reference_id=reference.id,
            verification_result_id=result.id,
            support_status=result.support_status,
            confidence=result.confidence,
            evidence_version=evidence_version,
            embedding_model_version=self.settings.embedding_model_version,
            prompt_version=self.settings.verification_prompt_version,
            verification_policy_version=self.settings.verification_policy_version,
            cache_source=cache_source,
        )
        db.add(cache)
        if commit:
            db.commit()
            db.refresh(cache)
        logger.info("cache_index_created", extra={"cache_id": cache.id, "verification_result_id": result.id, "doi": cache.doi})
        return cache

    def _resolve_reference_for_claim(self, claim: Claim, db: Session, *, reference_id: str | None = None) -> tuple[Reference | None, EvidencePackage | None]:
        if reference_id:
            reference = db.get(Reference, reference_id)
            if reference is None or reference.document_id != claim.document_id:
                raise AppException(status_code=404, code=ErrorCode.REFERENCE_NOT_FOUND, field="reference_id", detail=f"Reference '{reference_id}' was not found for this claim/document.", message="Reference not found")
            package = (
                db.query(EvidencePackage)
                .filter(EvidencePackage.claim_id == claim.id, EvidencePackage.reference_id == reference.id)
                .order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc())
                .first()
            )
            return reference, package

        package = (
            db.query(EvidencePackage)
            .filter(EvidencePackage.claim_id == claim.id)
            .order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc())
            .first()
        )
        if package:
            return db.get(Reference, package.reference_id), package

        link = (
            db.query(ClaimReferenceLink)
            .filter(ClaimReferenceLink.claim_id == claim.id, ClaimReferenceLink.reference_id.isnot(None))
            .order_by(ClaimReferenceLink.created_at.desc(), ClaimReferenceLink.id.desc())
            .first()
        )
        if link:
            return db.get(Reference, link.reference_id), None

        raise AppException(status_code=404, code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND, field="claim_id", detail="No mapped reference or evidence package was found for this claim.", message="Evidence package not found")

    def _resolve_doi(self, reference: Reference | None, evidence_package: EvidencePackage | None) -> str | None:
        if evidence_package and evidence_package.doi:
            return evidence_package.doi
        if reference and reference.extracted_doi:
            return reference.extracted_doi
        return None

    def _find_exact_cache(self, reference: Reference | None, key: CacheKey, db: Session) -> ClaimCacheIndex | None:
        if not reference or not key.normalized_doi:
            return None
        candidates = ClaimCacheRepository(db).find_exact_candidates(
            normalized_claim_hash=key.normalized_claim_hash,
            doi=key.normalized_doi,
            embedding_model_version=self.settings.embedding_model_version,
            prompt_version=self.settings.verification_prompt_version,
            verification_policy_version=self.settings.verification_policy_version,
            evidence_version=self.settings.cache_evidence_version,
            reference_id=reference.id if self.settings.cache_require_same_reference else None,
        )
        for cache in candidates:
            if self._is_eligible_for_reuse(cache):
                return cache
        return candidates[0] if candidates else None

    def _find_semantic_cache(self, reference: Reference | None, key: CacheKey, db: Session) -> dict[str, Any] | None:
        if not reference or not key.normalized_doi:
            return None
        candidates = ClaimCacheRepository(db).list_for_doi(doi=key.normalized_doi, verification_policy_version=self.settings.verification_policy_version)
        candidates = [item for item in candidates if not self.settings.cache_require_same_reference or item.reference_id == reference.id]
        matches = self.semantic_client.find_matches(claim_text=key.normalized_claim_text, doi=key.normalized_doi, candidates=candidates)
        if not matches:
            return None
        best = matches[0]
        cache: ClaimCacheIndex = best["cache_entry"]
        score = float(best["similarity_score"])
        if score >= self.settings.cache_high_similarity_threshold and self._is_eligible_for_reuse(cache):
            return self._decision_from_cache(None, reference, key, cache, similarity_score=score, exact=False)
        if score >= self.settings.cache_medium_similarity_threshold:
            return self._decision(
                claim=None,
                reference=reference,
                key=key,
                cache_hit=False,
                cache_source=CacheSource.NEW_VERIFICATION.value,
                recommended_action=CacheRecommendedAction.RERUN_VERIFICATION,
                matched_cache_id=cache.id,
                matched_result_id=cache.verification_result_id,
                similarity_score=score,
                confidence=cache.confidence,
                support_status=cache.support_status,
                reason="Medium semantic similarity found for the same DOI; rerun verification or send for review instead of reusing automatically.",
            )
        return None

    def _is_eligible_for_reuse(self, cache: ClaimCacheIndex) -> bool:
        if cache.deleted_at is not None:
            return False
        if cache.confidence is None or cache.confidence < self.settings.cache_min_confidence_to_reuse:
            return False
        if self.settings.cache_ttl_days > 0:
            created = cache.created_at
            if created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=UTC)
                if created < datetime.now(UTC) - timedelta(days=self.settings.cache_ttl_days):
                    return False
        return True

    def _decision_from_cache(self, claim: Claim | None, reference: Reference | None, key: CacheKey, cache: ClaimCacheIndex, *, similarity_score: float, exact: bool) -> dict[str, Any]:
        recommended_action = CacheRecommendedAction.REUSE_VERIFICATION
        reusable = True
        reason = "Exact normalized claim and DOI match with compatible policy version." if exact else "High semantic similarity for the same DOI with compatible policy version."

        if cache.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value:
            recommended_action = CacheRecommendedAction.NEEDS_HUMAN_REVIEW
            reusable = False
            reason = "A cached human-review result exists, but it must not be presented as a confident automated verification."
        elif cache.confidence is None or cache.confidence < self.settings.cache_min_confidence_to_reuse:
            recommended_action = CacheRecommendedAction.RERUN_VERIFICATION
            reusable = False
            reason = "Cached result confidence is below the configured reuse threshold."
        elif cache.support_status == SupportStatus.INSUFFICIENT_EVIDENCE.value:
            recommended_action = CacheRecommendedAction.RERUN_VERIFICATION
            reusable = False
            reason = "Cached result has insufficient evidence; rerun if newer evidence is available."
        elif self.settings.cache_ttl_days > 0 and _cache_age_days(cache) is not None and _cache_age_days(cache) > self.settings.cache_ttl_days:
            recommended_action = CacheRecommendedAction.RERUN_VERIFICATION
            reusable = False
            reason = "Cached result is older than the configured TTL and must be refreshed."

        return self._decision(
            claim=claim,
            reference=reference or cache.reference,
            key=key,
            cache_hit=True,
            cache_source=CacheSource.EXACT_CACHE.value if exact else CacheSource.SEMANTIC_CACHE.value,
            recommended_action=recommended_action,
            matched_cache_id=cache.id,
            matched_result_id=cache.verification_result_id,
            similarity_score=similarity_score,
            confidence=cache.confidence,
            support_status=cache.support_status,
            reason=reason,
            reusable=reusable,
            cache_age_days=_cache_age_days(cache),
        )

    def _decision(
        self,
        *,
        claim: Claim | None,
        reference: Reference | None,
        key: CacheKey,
        cache_hit: bool,
        cache_source: str,
        recommended_action: str,
        reason: str,
        matched_cache_id: str | None = None,
        matched_result_id: str | None = None,
        similarity_score: float | None = None,
        confidence: float | None = None,
        support_status: str | None = None,
        reusable: bool | None = None,
        cache_age_days: int | None = None,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim.id if claim else None,
            "reference_id": reference.id if reference else None,
            "doi": key.normalized_doi,
            "normalized_claim_hash": key.normalized_claim_hash,
            "normalized_claim_preview": key.normalized_claim_text[:160],
            "cache_hit": cache_hit,
            "cache_source": cache_source,
            "recommended_action": recommended_action,
            "matched_cache_id": matched_cache_id,
            "matched_result_id": matched_result_id,
            "similarity_score": similarity_score,
            "confidence": confidence,
            "support_status": support_status,
            "reusable": bool(cache_hit and recommended_action == CacheRecommendedAction.REUSE_VERIFICATION) if reusable is None else reusable,
            "cache_age_days": cache_age_days,
            "reason": reason,
            "policy": {
                "cache_enabled": self.settings.cache_enabled,
                "exact_cache_enabled": self.settings.cache_exact_enabled,
                "semantic_cache_enabled": self.settings.cache_semantic_enabled,
                "high_similarity_threshold": self.settings.cache_high_similarity_threshold,
                "medium_similarity_threshold": self.settings.cache_medium_similarity_threshold,
                "min_confidence_to_reuse": self.settings.cache_min_confidence_to_reuse,
                "ttl_days": self.settings.cache_ttl_days,
                "require_same_doi": self.settings.cache_require_same_doi,
                "require_same_policy_version": self.settings.cache_require_same_policy_version,
                "evidence_version": self.settings.cache_evidence_version,
                "embedding_model_version": self.settings.embedding_model_version,
                "prompt_version": self.settings.verification_prompt_version,
                "verification_policy_version": self.settings.verification_policy_version,
            },
            "phase": "BE-8",
            "processing_note": "BE-8 checks verification cache only. It does not call RAG, embeddings, GenAI verification, or final safety scoring.",
        }
