from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppException, ErrorCode
from app.models import Claim, ClaimCacheIndex, Reference, SourceMetadata, VerificationResult
from app.models.enums import CacheSource, DoiStatus, MetadataStatus
from app.repositories import DocumentRepository

logger = logging.getLogger(__name__)

# Semantic similarity thresholds (placeholder — real embeddings come with RAG merge).
SEMANTIC_HIGH_THRESHOLD = 0.92   # reuse result directly
SEMANTIC_MEDIUM_THRESHOLD = 0.75  # suggest but flag for human review

# Versioning — must match evidence_service.py constants so cache keys are stable.
EMBEDDING_MODEL_VERSION = "text-embedding-3-small-v1"
PROMPT_VERSION = "claim-verification-prompt-v1"
VERIFICATION_POLICY_VERSION = "policy-v1"
EVIDENCE_VERSION = "evidence-v1"


def _normalize_claim_text(text: str) -> str:
    """Canonical form used for exact-match hashing."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def _claim_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _cache_entry_to_dict(entry: ClaimCacheIndex, *, include_result: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "cache_id": entry.id,
        "normalized_claim_hash": entry.normalized_claim_hash,
        "normalized_claim_text": entry.normalized_claim_text,
        "doi": entry.doi,
        "reference_id": entry.reference_id,
        "verification_result_id": entry.verification_result_id,
        "support_status": entry.support_status,
        "confidence": entry.confidence,
        "cache_source": entry.cache_source,
        "evidence_version": entry.evidence_version,
        "embedding_model_version": entry.embedding_model_version,
        "prompt_version": entry.prompt_version,
        "verification_policy_version": entry.verification_policy_version,
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }
    if include_result and entry.verification_result:
        result = entry.verification_result
        data["verification_result"] = {
            "result_id": result.id,
            "support_status": result.support_status,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "limitations": result.limitations,
            "human_review_required": result.human_review_required,
            "evidence_availability": result.evidence_availability,
            "cache_source": result.cache_source,
        }
    return data


class VerificationCacheService:
    """BE-8 Verification Cache Layer.

    Provides exact-match cache lookup and a semantic cache placeholder.
    The semantic cache interface is defined here so the RAG/ML team can
    wire in real embeddings during the BE-9 merge without changing the
    call sites.

    Cache hit rules:
      - Exact hit (same normalized claim + same DOI) → reuse result directly
      - High semantic similarity (≥0.92, placeholder) → reuse with label
      - Medium semantic similarity (≥0.75, placeholder) → suggest, flag for human review
      - Different DOI → no reuse (different source, different evidence)
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def check_cache(
        self,
        claim_id: str,
        db: Session,
        *,
        reference_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Check the cache for a given claim (and optionally a specific reference).

        If reference_id is omitted, checks against all MAPPED references for
        this claim. Returns the best cache hit found, or a MISS result.
        """
        claim = db.get(Claim, claim_id)
        if not claim:
            raise AppException(
                status_code=404,
                code=ErrorCode.CLAIM_NOT_FOUND,
                field="claim_id",
                detail=f"Claim '{claim_id}' was not found.",
                message="Claim not found",
            )

        normalized_text = _normalize_claim_text(claim.claim_text)
        claim_hash = _claim_hash(normalized_text)

        # Collect candidate DOIs: from a specific reference or all mapped ones.
        doi_reference_pairs = self._get_doi_reference_pairs(claim_id, reference_id, db)

        if not doi_reference_pairs:
            return self._miss_response(claim, normalized_text, reason="no_mapped_references")

        # 1. Exact cache lookup.
        for doi, ref_id in doi_reference_pairs:
            if not doi:
                continue
            exact_hit = self._exact_lookup(claim_hash, doi, db)
            if exact_hit:
                logger.info(
                    "cache_exact_hit",
                    extra={"claim_id": claim_id, "doi": doi, "cache_id": exact_hit.id, "request_id": request_id},
                )
                return self._hit_response(
                    claim=claim,
                    normalized_text=normalized_text,
                    entry=exact_hit,
                    cache_type="EXACT",
                    reuse_recommended=True,
                    human_review_required=False,
                )

        # 2. Semantic cache lookup (placeholder — returns MISS until embeddings are wired in).
        for doi, ref_id in doi_reference_pairs:
            if not doi:
                continue
            semantic_result = self._semantic_lookup_placeholder(normalized_text, doi, db)
            if semantic_result:
                similarity, entry = semantic_result
                if similarity >= SEMANTIC_HIGH_THRESHOLD:
                    logger.info(
                        "cache_semantic_hit_high",
                        extra={"claim_id": claim_id, "doi": doi, "similarity": similarity, "request_id": request_id},
                    )
                    return self._hit_response(
                        claim=claim,
                        normalized_text=normalized_text,
                        entry=entry,
                        cache_type="SEMANTIC_HIGH",
                        reuse_recommended=True,
                        human_review_required=False,
                        similarity=similarity,
                    )
                if similarity >= SEMANTIC_MEDIUM_THRESHOLD:
                    logger.info(
                        "cache_semantic_hit_medium",
                        extra={"claim_id": claim_id, "doi": doi, "similarity": similarity, "request_id": request_id},
                    )
                    return self._hit_response(
                        claim=claim,
                        normalized_text=normalized_text,
                        entry=entry,
                        cache_type="SEMANTIC_MEDIUM",
                        reuse_recommended=False,
                        human_review_required=True,
                        similarity=similarity,
                    )

        logger.info("cache_miss", extra={"claim_id": claim_id, "request_id": request_id})
        return self._miss_response(claim, normalized_text, reason="no_cache_entry")

    def get_cache_result(self, claim_id: str, db: Session) -> dict[str, Any]:
        """Return the most recent cache entry for a claim."""
        claim = db.get(Claim, claim_id)
        if not claim:
            raise AppException(
                status_code=404,
                code=ErrorCode.CLAIM_NOT_FOUND,
                field="claim_id",
                detail=f"Claim '{claim_id}' was not found.",
                message="Claim not found",
            )

        normalized_text = _normalize_claim_text(claim.claim_text)
        claim_hash = _claim_hash(normalized_text)

        entry = db.scalar(
            select(ClaimCacheIndex)
            .where(ClaimCacheIndex.normalized_claim_hash == claim_hash)
            .order_by(ClaimCacheIndex.created_at.desc())
        )
        if not entry:
            raise AppException(
                status_code=404,
                code=ErrorCode.CLAIM_REFERENCE_LINK_NOT_FOUND,
                field="claim_id",
                detail=f"No cache entry found for claim '{claim_id}'.",
                message="Cache entry not found",
            )
        return {
            "claim_id": claim_id,
            "claim_text": claim.claim_text,
            "cache_entry": _cache_entry_to_dict(entry, include_result=True),
            "phase": "BE-8",
            "is_stub": False,
        }

    def store_cache_entry(
        self,
        *,
        claim: Claim,
        doi: str,
        reference_id: str,
        verification_result: VerificationResult,
        cache_source: str = CacheSource.NEW_VERIFICATION.value,
        db: Session,
    ) -> ClaimCacheIndex:
        """
        Store a new cache entry after a verification result is produced.
        Called by BE-9 (GenAI Verification Orchestration) after each verification.
        """
        normalized_text = _normalize_claim_text(claim.claim_text)
        claim_hash = _claim_hash(normalized_text)

        entry = ClaimCacheIndex(
            normalized_claim_hash=claim_hash,
            normalized_claim_text=normalized_text,
            doi=doi,
            reference_id=reference_id,
            verification_result_id=verification_result.id,
            support_status=verification_result.support_status,
            confidence=verification_result.confidence,
            evidence_version=EVIDENCE_VERSION,
            embedding_model_version=EMBEDDING_MODEL_VERSION,
            prompt_version=PROMPT_VERSION,
            verification_policy_version=VERIFICATION_POLICY_VERSION,
            cache_source=cache_source,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.info(
            "cache_entry_stored",
            extra={
                "claim_id": claim.id,
                "doi": doi,
                "cache_id": entry.id,
                "cache_source": cache_source,
            },
        )
        return entry

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_doi_reference_pairs(
        self,
        claim_id: str,
        reference_id: str | None,
        db: Session,
    ) -> list[tuple[str | None, str]]:
        """Return (doi, reference_id) pairs for the claim's mapped references."""
        from app.models import ClaimReferenceLink
        from app.models.enums import MappingStatus

        query = (
            select(ClaimReferenceLink)
            .where(
                ClaimReferenceLink.claim_id == claim_id,
                ClaimReferenceLink.mapping_status == MappingStatus.MAPPED.value,
                ClaimReferenceLink.reference_id.is_not(None),
            )
        )
        if reference_id:
            query = query.where(ClaimReferenceLink.reference_id == reference_id)

        links = list(db.scalars(query).all())
        pairs: list[tuple[str | None, str]] = []
        seen: set[str] = set()
        for link in links:
            ref_id = link.reference_id
            if ref_id in seen:
                continue
            seen.add(ref_id)
            reference = db.get(Reference, ref_id)
            doi = reference.extracted_doi if reference else None
            # Also check metadata for DOI resolved via title-search fallback.
            if not doi and reference:
                metadata = db.scalar(
                    select(SourceMetadata)
                    .where(
                        SourceMetadata.reference_id == ref_id,
                        SourceMetadata.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value,
                    )
                    .order_by(SourceMetadata.updated_at.desc())
                )
                if metadata:
                    doi = metadata.doi
            pairs.append((doi, ref_id))
        return pairs

    def _exact_lookup(self, claim_hash: str, doi: str, db: Session) -> ClaimCacheIndex | None:
        """Look up an exact cache hit by claim hash + DOI + version keys."""
        return db.scalar(
            select(ClaimCacheIndex)
            .where(
                ClaimCacheIndex.normalized_claim_hash == claim_hash,
                ClaimCacheIndex.doi == doi,
                ClaimCacheIndex.embedding_model_version == EMBEDDING_MODEL_VERSION,
                ClaimCacheIndex.prompt_version == PROMPT_VERSION,
                ClaimCacheIndex.verification_policy_version == VERIFICATION_POLICY_VERSION,
            )
            .order_by(ClaimCacheIndex.created_at.desc())
        )

    def _semantic_lookup_placeholder(
        self,
        normalized_text: str,
        doi: str,
        db: Session,
    ) -> tuple[float, ClaimCacheIndex] | None:
        """
        Placeholder for semantic similarity lookup.

        In production (post RAG-merge), this method will:
        1. Compute an embedding for normalized_text via the embedding service
        2. Query the vector store for similar embeddings with the same DOI
        3. Return (similarity_score, cache_entry) for the best match

        Until embeddings are available, this always returns None (cache miss).
        The interface is stable so BE-9 / RAG team can wire in real logic here.
        """
        return None

    def _hit_response(
        self,
        *,
        claim: Claim,
        normalized_text: str,
        entry: ClaimCacheIndex,
        cache_type: str,
        reuse_recommended: bool,
        human_review_required: bool,
        similarity: float | None = None,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim.id,
            "claim_text": claim.claim_text,
            "normalized_claim_text": normalized_text,
            "cache_hit": True,
            "cache_type": cache_type,
            "reuse_recommended": reuse_recommended,
            "human_review_required": human_review_required,
            "similarity_score": similarity,
            "cache_rule": self._cache_rule_label(cache_type),
            "cache_entry": _cache_entry_to_dict(entry, include_result=True),
            "phase": "BE-8",
            "is_stub": False,
            "processing_note": (
                "Cache hit found. If reuse_recommended=true, the cached verification "
                "result can be reused directly. If human_review_required=true, the "
                "result should be reviewed before presenting to the user."
            ),
        }

    def _miss_response(
        self,
        claim: Claim,
        normalized_text: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim.id,
            "claim_text": claim.claim_text,
            "normalized_claim_text": normalized_text,
            "cache_hit": False,
            "cache_type": None,
            "reuse_recommended": False,
            "human_review_required": False,
            "similarity_score": None,
            "cache_rule": "MISS — run full verification via BE-9",
            "cache_entry": None,
            "miss_reason": reason,
            "phase": "BE-8",
            "is_stub": False,
            "processing_note": (
                "No cache entry found for this claim + DOI combination. "
                "A full verification run (BE-9) is required."
            ),
        }

    def _cache_rule_label(self, cache_type: str) -> str:
        return {
            "EXACT": "Exact hit — reuse result directly",
            "SEMANTIC_HIGH": "High semantic similarity — reuse result with label",
            "SEMANTIC_MEDIUM": "Medium semantic similarity — suggest but rerun or human review",
        }.get(cache_type, "Unknown")
