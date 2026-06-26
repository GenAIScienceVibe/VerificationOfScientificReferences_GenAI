from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import EvidencePackage, RagRetrievalResult, Reference, SafetyCheck, VerificationResult
from app.models.enums import CacheSource, DoiStatus, EvidenceAvailability, MetadataStatus, SafetyRiskLevel, SupportStatus

logger = logging.getLogger(__name__)

SAFETY_STATUS_PASS = "PASS"
SAFETY_STATUS_WARNING = "WARNING"
SAFETY_STATUS_BLOCKED = "BLOCKED"
SAFETY_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"

_STATUS_PRIORITY = {
    SupportStatus.SUPPORTED.value: 0,
    SupportStatus.PARTIALLY_SUPPORTED.value: 1,
    SupportStatus.NOT_SUPPORTED.value: 1,
    SupportStatus.INSUFFICIENT_EVIDENCE.value: 2,
    SupportStatus.NEEDS_HUMAN_REVIEW.value: 3,
}
_RISK_PRIORITY = {
    SafetyRiskLevel.LOW.value: 0,
    SafetyRiskLevel.UNKNOWN.value: 0,
    SafetyRiskLevel.MEDIUM.value: 1,
    SafetyRiskLevel.HIGH.value: 2,
}


@dataclass(frozen=True)
class SafetyRuleHit:
    rule: str
    issue: str
    recommended_action: str
    risk_level: str = SafetyRiskLevel.MEDIUM.value
    safety_status: str = SAFETY_STATUS_NEEDS_REVIEW
    final_support_status: str | None = None
    confidence_cap: float | None = None
    human_review_required: bool = True


@dataclass
class SafetyDecision:
    final_support_status: str
    final_confidence: float
    human_review_required: bool
    risk_level: str
    safety_status: str
    rules_triggered: list[str]
    reason: str
    recommended_action: str
    limitations: str
    checks_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_support_status": self.final_support_status,
            "final_confidence": self.final_confidence,
            "human_review_required": self.human_review_required,
            "risk_level": self.risk_level,
            "safety_status": self.safety_status,
            "rules_triggered": self.rules_triggered,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "limitations": self.limitations,
            "checks_created": self.checks_created,
        }


class SafetyPolicyService:
    """BE-11 deterministic safety and confidence policy engine.

    This service is intentionally backend-controlled and deterministic. It does
    not call GenAI, RAG, external metadata APIs, or publisher websites.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate_and_apply(
        self,
        result: VerificationResult,
        db: Session,
        *,
        evidence_package: EvidencePackage | None = None,
        retrieval: RagRetrievalResult | None = None,
        extra_rule: SafetyRuleHit | dict[str, Any] | None = None,
        replace_existing_checks: bool = False,
        request_id: str | None = None,
    ) -> SafetyDecision:
        """Evaluate safety rules, update the result, and persist SafetyCheck rows."""
        try:
            reference = result.reference or db.get(Reference, result.reference_id)
            package = evidence_package or self._latest_evidence_package_for_result(result, db)
            retrieval = retrieval or self._latest_retrieval_for_result(result, db)
            hits = self.evaluate(result, reference=reference, evidence_package=package, retrieval=retrieval, extra_rule=extra_rule)
            decision = self._apply_decision_to_result(result, hits)

            if replace_existing_checks:
                db.execute(delete(SafetyCheck).where(SafetyCheck.verification_result_id == result.id))
                db.flush()
            created = self._store_safety_checks(result, db, hits)
            decision.checks_created = created
            db.flush()
            logger.info(
                "safety_evaluation_completed",
                extra={
                    "request_id": request_id,
                    "result_id": result.id,
                    "document_id": result.document_id,
                    "claim_id": result.claim_id,
                    "reference_id": result.reference_id,
                    "rules_triggered": decision.rules_triggered,
                    "final_support_status": decision.final_support_status,
                    "final_confidence": decision.final_confidence,
                },
            )
            return decision
        except Exception as exc:
            logger.exception("safety_evaluation_failed", extra={"request_id": request_id, "result_id": getattr(result, "id", None)})
            if isinstance(exc, AppException):
                raise
            raise AppException(status_code=500, code=ErrorCode.SAFETY_EVALUATION_FAILED, field="result_id", detail="Safety evaluation failed for the requested verification result.", message="Safety evaluation failed") from exc

    def evaluate(
        self,
        result: VerificationResult,
        *,
        reference: Reference | None,
        evidence_package: EvidencePackage | None,
        retrieval: RagRetrievalResult | None,
        extra_rule: SafetyRuleHit | dict[str, Any] | None = None,
    ) -> list[SafetyRuleHit]:
        hits: list[SafetyRuleHit] = []

        def add(hit: SafetyRuleHit) -> None:
            hits.append(hit)
            logger.info(
                "safety_rule_triggered",
                extra={
                    "result_id": result.id,
                    "document_id": result.document_id,
                    "claim_id": result.claim_id,
                    "reference_id": result.reference_id,
                    "rule": hit.rule,
                    "risk_level": hit.risk_level,
                },
            )

        extra = self._coerce_extra_rule(extra_rule)
        if extra:
            add(extra)

        doi_status = self._doi_status(result, reference, evidence_package)
        if doi_status == DoiStatus.MISSING.value:
            add(SafetyRuleHit(
                rule="DOI_MISSING",
                issue="The cited source does not contain a DOI, so the system cannot reliably verify the cited source through DOI metadata.",
                recommended_action="Human reviewer should manually inspect the cited source.",
                risk_level=SafetyRiskLevel.HIGH.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=0.50,
            ))
        elif doi_status == DoiStatus.INVALID.value:
            add(SafetyRuleHit(
                rule="DOI_INVALID",
                issue="The DOI could not be validated against metadata sources.",
                recommended_action="Check whether the citation uses the correct DOI or source.",
                risk_level=SafetyRiskLevel.HIGH.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=0.50,
            ))
        elif doi_status == DoiStatus.MALFORMED.value:
            add(SafetyRuleHit(
                rule="DOI_MALFORMED",
                issue="The DOI format is malformed and cannot be reliably verified.",
                recommended_action="Correct the DOI or inspect the reference manually.",
                risk_level=SafetyRiskLevel.HIGH.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=0.50,
            ))

        metadata_status = (reference.metadata_status if reference else None) or None
        if metadata_status in {MetadataStatus.METADATA_UNAVAILABLE.value, MetadataStatus.LOOKUP_FAILED.value}:
            add(SafetyRuleHit(
                rule="METADATA_UNAVAILABLE",
                issue="Official metadata could not be retrieved for the cited source.",
                recommended_action="Human reviewer should verify source metadata manually before trusting the result.",
                risk_level=SafetyRiskLevel.MEDIUM.value,
                final_support_status=SupportStatus.INSUFFICIENT_EVIDENCE.value,
                confidence_cap=max(self.settings.safety_max_confidence_with_metadata_only, 0.50),
            ))

        evidence_availability = (evidence_package.evidence_availability if evidence_package else result.evidence_availability) or EvidenceAvailability.SOURCE_UNAVAILABLE.value
        if evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value and self.settings.safety_flag_source_unavailable:
            add(SafetyRuleHit(
                rule="SOURCE_UNAVAILABLE",
                issue="No usable source evidence was available for this claim-reference pair.",
                recommended_action="Retrieve source evidence or manually inspect the cited source.",
                risk_level=SafetyRiskLevel.HIGH.value,
                final_support_status=SupportStatus.INSUFFICIENT_EVIDENCE.value,
                confidence_cap=self.settings.safety_max_confidence_with_source_unavailable,
            ))
        elif evidence_availability == EvidenceAvailability.METADATA_ONLY.value and result.support_status == SupportStatus.SUPPORTED.value and self.settings.safety_flag_metadata_only_supported:
            add(SafetyRuleHit(
                rule="METADATA_ONLY_SUPPORTED",
                issue="Only metadata-level evidence was available; claim-level support cannot be fully verified.",
                recommended_action="Human reviewer should inspect abstract/full text before accepting support.",
                risk_level=SafetyRiskLevel.MEDIUM.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=self.settings.safety_max_confidence_with_metadata_only,
            ))

        similarity = result.overall_similarity_score
        if retrieval and retrieval.overall_similarity_score is not None:
            similarity = retrieval.overall_similarity_score
        if similarity is not None:
            if similarity < self.settings.safety_low_similarity_threshold:
                add(SafetyRuleHit(
                    rule="LOW_SIMILARITY",
                    issue="Retrieved evidence similarity was below the backend safety threshold.",
                    recommended_action="Human reviewer should inspect the cited source and retrieved evidence.",
                    risk_level=SafetyRiskLevel.HIGH.value,
                    final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                    confidence_cap=self.settings.safety_max_confidence_with_low_similarity,
                ))
            elif similarity < self.settings.safety_min_strong_similarity and result.support_status == SupportStatus.SUPPORTED.value:
                add(SafetyRuleHit(
                    rule="MEDIUM_SIMILARITY_SUPPORTED",
                    issue="The result was marked supported, but retrieved evidence similarity was only medium.",
                    recommended_action="Treat this result as partial or review-required until stronger evidence is available.",
                    risk_level=SafetyRiskLevel.MEDIUM.value,
                    final_support_status=SupportStatus.PARTIALLY_SUPPORTED.value,
                    confidence_cap=0.75,
                    human_review_required=True,
                    safety_status=SAFETY_STATUS_WARNING,
                ))

        confidence = float(result.confidence or 0.0)
        if confidence < self.settings.safety_min_genai_confidence and result.verification_method != "CACHE_ONLY":
            add(SafetyRuleHit(
                rule="LOW_GENAI_CONFIDENCE",
                issue="GenAI confidence is below the backend minimum confidence threshold.",
                recommended_action="Human reviewer should inspect the claim and cited source.",
                risk_level=SafetyRiskLevel.MEDIUM.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=confidence,
            ))

        if self.settings.safety_enable_genai_rag_conflict_check:
            if result.support_status == SupportStatus.SUPPORTED.value and ((similarity or 0.0) < self.settings.safety_min_acceptable_similarity or result.evidence_used_count <= 0):
                add(SafetyRuleHit(
                    rule="GENAI_SUPPORTED_BUT_WEAK_EVIDENCE",
                    issue="GenAI marked the claim as supported, but retrieved evidence was weak or missing.",
                    recommended_action="Human reviewer should inspect the cited source and retrieved evidence.",
                    risk_level=SafetyRiskLevel.HIGH.value,
                    final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                    confidence_cap=self.settings.safety_max_confidence_with_low_similarity,
                ))

        evidence_used_mismatch = self._evidence_used_mismatch(result, retrieval)
        if evidence_used_mismatch:
            add(SafetyRuleHit(
                rule="EVIDENCE_USED_MISMATCH",
                issue="GenAI referenced evidence chunks that were not retrieved.",
                recommended_action="Discard this automated result and rerun verification or inspect manually.",
                risk_level=SafetyRiskLevel.HIGH.value,
                final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                confidence_cap=self.settings.safety_max_confidence_with_low_similarity,
            ))

        if result.cache_source in {CacheSource.EXACT_CACHE.value, CacheSource.SEMANTIC_CACHE.value, CacheSource.HUMAN_CORRECTED.value}:
            if result.source_result and reference:
                source_doi = self._normalize_doi(result.source_result.reference.extracted_doi if result.source_result.reference else None)
                current_doi = self._normalize_doi(reference.extracted_doi)
                if source_doi and current_doi and source_doi != current_doi:
                    add(SafetyRuleHit(
                        rule="CACHE_DIFFERENT_DOI",
                        issue="Cached result DOI does not match the current reference DOI.",
                        recommended_action="Do not reuse cache; run a new verification.",
                        risk_level=SafetyRiskLevel.HIGH.value,
                        final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                        confidence_cap=0.0,
                    ))
            if confidence < self.settings.cache_min_confidence_to_reuse:
                add(SafetyRuleHit(
                    rule="CACHE_LOW_CONFIDENCE",
                    issue="Cached result confidence is below the cache reuse threshold.",
                    recommended_action="Run a fresh verification or require human review.",
                    risk_level=SafetyRiskLevel.MEDIUM.value,
                    final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                    confidence_cap=confidence,
                ))
            if result.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value:
                add(SafetyRuleHit(
                    rule="CACHE_NEEDS_HUMAN_REVIEW",
                    issue="Cached result already required human review and must not be presented as a confident verification.",
                    recommended_action="Human reviewer should inspect this cached result.",
                    risk_level=SafetyRiskLevel.MEDIUM.value,
                    final_support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
                    confidence_cap=min(confidence, 0.60),
                ))

        return hits

    def get_safety_checks_for_result(self, result_id: str, db: Session) -> dict[str, Any]:
        result = db.get(VerificationResult, result_id)
        if result is None:
            raise AppException(status_code=404, code=ErrorCode.VERIFICATION_RESULT_NOT_FOUND, field="result_id", detail="Verification result was not found.", message="Verification result not found")
        checks = db.scalars(select(SafetyCheck).where(SafetyCheck.verification_result_id == result.id).order_by(SafetyCheck.created_at, SafetyCheck.id)).all()
        return {"result_id": result.id, "checks": [self.safety_check_to_dict(item) for item in checks]}

    def get_document_safety_summary(self, document_id: str, db: Session) -> dict[str, Any]:
        results = db.scalars(
            select(VerificationResult)
            .options(selectinload(VerificationResult.safety_checks))
            .where(VerificationResult.document_id == document_id)
            .order_by(VerificationResult.created_at.desc())
        ).all()
        if not results:
            return {"document_id": document_id, "total_results": 0, "low_risk": 0, "medium_risk": 0, "high_risk": 0, "human_review_required": 0, "top_triggered_rules": []}
        rule_counts: dict[str, int] = {}
        low = medium = high = 0
        for result in results:
            risk = self.highest_risk(result.safety_checks)
            if risk == SafetyRiskLevel.HIGH.value:
                high += 1
            elif risk == SafetyRiskLevel.MEDIUM.value:
                medium += 1
            else:
                low += 1
            for check in result.safety_checks:
                rule_counts[check.backend_rule_triggered or "UNKNOWN"] = rule_counts.get(check.backend_rule_triggered or "UNKNOWN", 0) + 1
        top_rules = [{"rule": rule, "count": count} for rule, count in sorted(rule_counts.items(), key=lambda x: (-x[1], x[0]))[:10]]
        return {
            "document_id": document_id,
            "total_results": len(results),
            "low_risk": low,
            "medium_risk": medium,
            "high_risk": high,
            "human_review_required": sum(1 for item in results if item.human_review_required),
            "top_triggered_rules": top_rules,
        }

    @staticmethod
    def safety_check_to_dict(check: SafetyCheck) -> dict[str, Any]:
        return {
            "safety_check_id": check.id,
            "verification_result_id": check.verification_result_id,
            "safety_status": check.safety_status,
            "risk_level": check.risk_level,
            "issue": check.issue,
            "recommended_action": check.recommended_action,
            "backend_rule_triggered": check.backend_rule_triggered,
            "created_at": check.created_at.isoformat().replace("+00:00", "Z") if check.created_at else None,
        }

    @staticmethod
    def highest_risk(checks: list[SafetyCheck]) -> str:
        if not checks:
            return SafetyRiskLevel.LOW.value
        return max((check.risk_level for check in checks), key=lambda risk: _RISK_PRIORITY.get(risk, 0))

    def _apply_decision_to_result(self, result: VerificationResult, hits: list[SafetyRuleHit]) -> SafetyDecision:
        original_status = result.support_status
        original_confidence = float(result.confidence or 0.0)
        final_status = original_status if original_status in _STATUS_PRIORITY else SupportStatus.NEEDS_HUMAN_REVIEW.value
        confidence = min(max(original_confidence, 0.0), 1.0)
        human_review = bool(result.human_review_required)
        caps: list[float] = []
        reasons: list[str] = []
        actions: list[str] = []
        rules: list[str] = []
        risk = SafetyRiskLevel.LOW.value
        safety_status = SAFETY_STATUS_PASS
        for hit in hits:
            rules.append(hit.rule)
            reasons.append(hit.issue)
            actions.append(hit.recommended_action)
            risk = max([risk, hit.risk_level], key=lambda value: _RISK_PRIORITY.get(value, 0))
            if hit.safety_status == SAFETY_STATUS_BLOCKED:
                safety_status = SAFETY_STATUS_BLOCKED
            elif hit.safety_status == SAFETY_STATUS_NEEDS_REVIEW and safety_status != SAFETY_STATUS_BLOCKED:
                safety_status = SAFETY_STATUS_NEEDS_REVIEW
            elif hit.safety_status == SAFETY_STATUS_WARNING and safety_status == SAFETY_STATUS_PASS:
                safety_status = SAFETY_STATUS_WARNING
            if hit.final_support_status and _STATUS_PRIORITY.get(hit.final_support_status, 0) > _STATUS_PRIORITY.get(final_status, 0):
                final_status = hit.final_support_status
            elif hit.final_support_status == SupportStatus.PARTIALLY_SUPPORTED.value and final_status == SupportStatus.SUPPORTED.value:
                final_status = SupportStatus.PARTIALLY_SUPPORTED.value
            if hit.confidence_cap is not None:
                caps.append(float(hit.confidence_cap))
            if hit.human_review_required:
                human_review = True
        if caps:
            cap = min(max(min(caps), 0.0), 1.0)
            if confidence > cap:
                logger.info("safety_confidence_capped", extra={"result_id": result.id, "from_confidence": confidence, "to_confidence": cap})
            confidence = min(confidence, cap)
        if final_status in {SupportStatus.NEEDS_HUMAN_REVIEW.value, SupportStatus.INSUFFICIENT_EVIDENCE.value}:
            human_review = True
        result.support_status = final_status
        result.confidence = confidence
        result.human_review_required = human_review
        if hits:
            safety_limitation = "Safety rules triggered: " + "; ".join(rules)
            existing = result.limitations or ""
            result.limitations = (existing + "\n" + safety_limitation).strip()
            if final_status != original_status:
                logger.info("safety_status_overridden", extra={"result_id": result.id, "from_status": original_status, "to_status": final_status})
        return SafetyDecision(
            final_support_status=final_status,
            final_confidence=confidence,
            human_review_required=human_review,
            risk_level=risk,
            safety_status=safety_status,
            rules_triggered=rules,
            reason="; ".join(reasons) if reasons else "No deterministic safety rule was triggered.",
            recommended_action="; ".join(dict.fromkeys(actions)) if actions else "No action required by BE-11 safety policy.",
            limitations=result.limitations or "",
        )

    def _store_safety_checks(self, result: VerificationResult, db: Session, hits: list[SafetyRuleHit]) -> int:
        for hit in hits:
            db.add(SafetyCheck(
                verification_result_id=result.id,
                safety_status=hit.safety_status,
                risk_level=hit.risk_level,
                issue=hit.issue,
                recommended_action=hit.recommended_action,
                backend_rule_triggered=hit.rule,
            ))
        return len(hits)

    def _latest_evidence_package_for_result(self, result: VerificationResult, db: Session) -> EvidencePackage | None:
        return db.scalars(
            select(EvidencePackage)
            .where(EvidencePackage.claim_id == result.claim_id, EvidencePackage.reference_id == result.reference_id)
            .order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc())
        ).first()

    def _latest_retrieval_for_result(self, result: VerificationResult, db: Session) -> RagRetrievalResult | None:
        return db.scalars(
            select(RagRetrievalResult)
            .where(RagRetrievalResult.claim_id == result.claim_id, RagRetrievalResult.reference_id == result.reference_id)
            .order_by(RagRetrievalResult.created_at.desc(), RagRetrievalResult.id.desc())
        ).first()

    def _doi_status(self, result: VerificationResult, reference: Reference | None, package: EvidencePackage | None) -> str | None:
        if package and package.doi_status:
            return package.doi_status
        if reference and reference.doi_status:
            return reference.doi_status
        return None

    def _evidence_used_mismatch(self, result: VerificationResult, retrieval: RagRetrievalResult | None) -> bool:
        if not retrieval:
            return False
        used = result.evidence_used_json or []
        if not used:
            return False
        chunks = retrieval.top_chunks_json or []
        available = {str(chunk.get("chunk_id")) for chunk in chunks if isinstance(chunk, dict) and chunk.get("chunk_id")}
        return any(str(chunk_id) not in available for chunk_id in used)

    def _coerce_extra_rule(self, extra_rule: SafetyRuleHit | dict[str, Any] | None) -> SafetyRuleHit | None:
        if extra_rule is None:
            return None
        if isinstance(extra_rule, SafetyRuleHit):
            return extra_rule
        rule = str(extra_rule.get("rule") or extra_rule.get("backend_rule_triggered") or "SAFETY_RULE_TRIGGERED")
        issue = str(extra_rule.get("issue") or extra_rule.get("reason") or "Backend safety rule was triggered.")
        return SafetyRuleHit(
            rule=rule,
            issue=issue,
            recommended_action=str(extra_rule.get("recommended_action") or "Human reviewer should inspect this result."),
            risk_level=str(extra_rule.get("risk_level") or SafetyRiskLevel.HIGH.value),
            safety_status=str(extra_rule.get("safety_status") or SAFETY_STATUS_NEEDS_REVIEW),
            final_support_status=extra_rule.get("final_support_status"),
            confidence_cap=extra_rule.get("confidence_cap"),
            human_review_required=bool(extra_rule.get("human_review_required", True)),
        )

    @staticmethod
    def _normalize_doi(value: str | None) -> str | None:
        if not value:
            return None
        raw = value.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
        return raw.strip().rstrip(".,;)") or None
