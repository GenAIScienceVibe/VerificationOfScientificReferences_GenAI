from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.errors import AppException, ErrorCode
from app.models import (
    Claim,
    ClaimReferenceLink,
    Document,
    EvidencePackage,
    PipelineRun,
    PipelineStep,
    PromptRun,
    RagRetrievalResult,
    Reference,
    SafetyCheck,
    VerificationResult,
)
from app.models.enums import (
    CacheSource,
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    PipelineStatus,
    PipelineStepStatus,
    RetrievalStatus,
    SafetyRiskLevel,
    SupportStatus,
)
from app.services.evidence_package_builder import EvidencePackageBuilder
from app.services.genai_verification import GenAiVerificationService
from app.services.rag_ml_integration import RagRetrievalService
from app.services.safety_policy import SafetyPolicyService, SafetyRuleHit
from app.services.verification_cache import CacheRecommendedAction, VerificationCacheService

logger = logging.getLogger(__name__)

PIPELINE_STEPS = [
    "TEXT_EXTRACTION",
    "REFERENCE_EXTRACTION",
    "DOI_METADATA_LOOKUP",
    "CLAIM_EXTRACTION",
    "EVIDENCE_PACKAGE_CREATION",
    "CACHE_CHECK",
    "RAG_RETRIEVAL",
    "GENAI_VERIFICATION",
    "BASIC_SAFETY_CHECK",
    "RESULT_STORAGE",
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


class VerificationOrchestrator:
    """BE-10 synchronous MVP document verification orchestrator."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache_service = VerificationCacheService(settings=self.settings)
        self.rag_service = RagRetrievalService(settings=self.settings)
        self.genai_service = GenAiVerificationService(settings=self.settings)
        self.evidence_builder = EvidencePackageBuilder(self.settings)
        self.safety_service = SafetyPolicyService(settings=self.settings)

    def run_document_verification(
        self,
        document_id: str,
        db: Session,
        *,
        mode: str = "FULL_VERIFICATION",
        use_cache: bool = True,
        use_rag: bool = True,
        use_genai_safety_review: bool = True,
        generate_report: bool = False,
        claim_ids: list[str] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document was not found.", message="Document not found")

        run = PipelineRun(
            document_id=document.id,
            mode=mode or "FULL_VERIFICATION",
            status=PipelineStatus.RUNNING.value,
            progress_percentage=0,
            current_step="STARTED",
            use_cache=use_cache,
            use_rag=use_rag,
            use_genai_safety_review=use_genai_safety_review,
            generate_report=generate_report,
            started_at=_utc_now(),
            warnings_json=[],
        )
        db.add(run)
        db.flush()
        document.latest_pipeline_run_id = run.id
        document.status = DocumentStatus.VERIFYING.value
        steps = self._create_steps(run, db)
        db.commit()
        db.refresh(run)

        logger.info("verification_pipeline_start", extra={"request_id": request_id, "document_id": document.id, "pipeline_run_id": run.id})
        warnings: list[str] = []
        created_results: list[VerificationResult] = []
        try:
            self._mark_step(steps["TEXT_EXTRACTION"], PipelineStepStatus.SUCCEEDED.value, db, progress=10, metadata={"status": document.status})
            self._require_text(document)
            self._mark_step(steps["REFERENCE_EXTRACTION"], PipelineStepStatus.SUCCEEDED.value, db, progress=20, metadata={"references_count": document.references_count})
            self._require_references(document, db)
            self._mark_step(steps["DOI_METADATA_LOOKUP"], PipelineStepStatus.SUCCEEDED.value, db, progress=30, metadata={"note": "BE-10 reuses existing BE-5 metadata when present."})
            self._mark_step(steps["CLAIM_EXTRACTION"], PipelineStepStatus.SUCCEEDED.value, db, progress=40, metadata={"claims_count": document.claims_count})
            self._require_claims(document, db)

            self._mark_step(steps["EVIDENCE_PACKAGE_CREATION"], PipelineStepStatus.RUNNING.value, db, progress=45)
            packages = self._ensure_evidence_packages(document, db)
            self._mark_step(steps["EVIDENCE_PACKAGE_CREATION"], PipelineStepStatus.SUCCEEDED.value, db, progress=50, metadata={"evidence_packages": len(packages)})

            eligible_packages = self._latest_packages_for_verification(document, db)
            if claim_ids is not None:
                eligible_packages = [p for p in eligible_packages if p.claim_id in set(claim_ids)]
            if not eligible_packages:
                raise AppException(status_code=422, code=ErrorCode.EVIDENCE_PACKAGE_NOT_FOUND, field="document_id", detail="No evidence packages are available for verification.", message="Evidence packages missing")

            for index, package in enumerate(eligible_packages, start=1):
                result = self._verify_package(
                    package,
                    run,
                    steps,
                    db,
                    use_cache=use_cache,
                    use_rag=use_rag,
                    request_id=request_id,
                    warnings=warnings,
                )
                created_results.append(result)
                run.progress_percentage = min(95, 50 + int(index / max(len(eligible_packages), 1) * 40))
                db.flush()

            status = PipelineStatus.SUCCEEDED.value if created_results else PipelineStatus.FAILED.value
            if warnings:
                status = PipelineStatus.PARTIAL_FAILED.value if created_results else PipelineStatus.FAILED.value
            run.status = status
            run.progress_percentage = 100
            run.current_step = "COMPLETED"
            run.completed_at = _utc_now()
            run.warnings_json = warnings
            document.status = DocumentStatus.VERIFIED.value if created_results else DocumentStatus.PARTIAL_FAILED.value
            self._mark_step(steps["RESULT_STORAGE"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata={"results_created": len(created_results)})
            db.commit()
        except Exception as exc:
            run.status = PipelineStatus.FAILED.value
            run.current_step = "FAILED"
            run.error_message = str(exc)
            run.completed_at = _utc_now()
            document.status = DocumentStatus.PARTIAL_FAILED.value
            failing_step = run.current_step or "UNKNOWN"
            logger.exception("verification_pipeline_failed", extra={"document_id": document.id, "pipeline_run_id": run.id, "step": failing_step})
            db.commit()
            if isinstance(exc, AppException):
                raise
            raise AppException(status_code=500, code=ErrorCode.VERIFICATION_FAILED, field="document_id", detail="Verification workflow failed for the requested document.", message="Verification failed") from exc

        return self.get_pipeline_run(run.id, db)

    def get_pipeline_run(self, pipeline_run_id: str, db: Session) -> dict[str, Any]:
        run = db.get(PipelineRun, pipeline_run_id)
        if run is None:
            raise AppException(status_code=404, code=ErrorCode.PIPELINE_RUN_NOT_FOUND, field="pipeline_run_id", detail="Pipeline run was not found.", message="Pipeline run not found")
        return {
            "pipeline_run_id": run.id,
            "document_id": run.document_id,
            "mode": run.mode,
            "status": run.status,
            "progress_percentage": run.progress_percentage,
            "current_step": run.current_step,
            "use_cache": run.use_cache,
            "use_rag": run.use_rag,
            "use_genai_safety_review": run.use_genai_safety_review,
            "generate_report": run.generate_report,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
            "warnings": run.warnings_json or [],
            "error_message": run.error_message,
            "phase": "BE-11",
        }

    def get_pipeline_steps(self, pipeline_run_id: str, db: Session) -> dict[str, Any]:
        run = db.get(PipelineRun, pipeline_run_id)
        if run is None:
            raise AppException(status_code=404, code=ErrorCode.PIPELINE_RUN_NOT_FOUND, field="pipeline_run_id", detail="Pipeline run was not found.", message="Pipeline run not found")
        steps = db.scalars(select(PipelineStep).where(PipelineStep.pipeline_run_id == run.id).order_by(PipelineStep.created_at, PipelineStep.id)).all()
        return {
            "pipeline_run_id": run.id,
            "steps": [
                {
                    "pipeline_step_id": step.id,
                    "step_name": step.step_name,
                    "status": step.status,
                    "progress_percentage": step.progress_percentage,
                    "started_at": _iso(step.started_at),
                    "completed_at": _iso(step.completed_at),
                    "error_message": step.error_message,
                    "metadata": step.metadata_json,
                }
                for step in steps
            ],
        }

    def list_document_verification_results(
        self,
        document_id: str,
        db: Session,
        *,
        support_status: str | None = None,
        human_review_required: bool | None = None,
        cache_source: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document was not found.", message="Document not found")
        statement = (
            select(VerificationResult)
            .options(selectinload(VerificationResult.claim), selectinload(VerificationResult.reference), selectinload(VerificationResult.safety_checks))
            .where(VerificationResult.document_id == document.id)
            .order_by(VerificationResult.created_at.desc(), VerificationResult.id.desc())
        )
        results = list(db.scalars(statement).all())
        latest: dict[tuple[str, str], VerificationResult] = {}
        for result in results:
            key = (result.claim_id, result.reference_id)
            if key not in latest:
                latest[key] = result
        results = list(latest.values())
        if support_status:
            results = [item for item in results if item.support_status == support_status]
        if human_review_required is not None:
            results = [item for item in results if item.human_review_required is human_review_required]
        if cache_source:
            results = [item for item in results if item.cache_source == cache_source]
        summary = self._summary(results, document.claims_count)
        total = len(results)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        page_items = results[(page - 1) * page_size : page * page_size]
        return {"document_id": document.id, "summary": summary, "total": total, "page": page, "page_size": page_size, "results": [self.result_to_dict(item, include_details=False) for item in page_items]}

    def get_verification_result(self, result_id: str, db: Session) -> dict[str, Any]:
        result = db.get(VerificationResult, result_id)
        if result is None:
            raise AppException(status_code=404, code=ErrorCode.VERIFICATION_RESULT_NOT_FOUND, field="result_id", detail="Verification result was not found.", message="Verification result not found")
        return self.result_to_dict(result, include_details=True)

    def _create_steps(self, run: PipelineRun, db: Session) -> dict[str, PipelineStep]:
        steps: dict[str, PipelineStep] = {}
        for name in PIPELINE_STEPS:
            step = PipelineStep(pipeline_run_id=run.id, step_name=name, status=PipelineStepStatus.PENDING.value, progress_percentage=0)
            db.add(step)
            steps[name] = step
        db.flush()
        return steps

    def _mark_step(self, step: PipelineStep, status: str, db: Session, *, progress: int = 100, metadata: dict[str, Any] | None = None, error: str | None = None) -> None:
        if step.started_at is None:
            step.started_at = _utc_now()
        step.status = status
        step.progress_percentage = progress
        if status in {PipelineStepStatus.SUCCEEDED.value, PipelineStepStatus.FAILED.value, PipelineStepStatus.PARTIAL_FAILED.value, PipelineStepStatus.SKIPPED.value}:
            step.completed_at = _utc_now()
        if metadata is not None:
            step.metadata_json = metadata
        if error is not None:
            step.error_message = error
        db.flush()

    def _require_text(self, document: Document) -> None:
        if not document.cleaned_text:
            raise AppException(status_code=422, code=ErrorCode.DOCUMENT_TEXT_NOT_FOUND, field="document_id", detail="Document does not have processed text.", message="Document text missing")

    def _require_references(self, document: Document, db: Session) -> None:
        count = db.query(Reference).filter(Reference.document_id == document.id).count()
        if count <= 0:
            raise AppException(status_code=422, code=ErrorCode.REFERENCES_NOT_FOUND, field="document_id", detail="Document has no extracted references.", message="References missing")

    def _require_claims(self, document: Document, db: Session) -> None:
        count = db.query(Claim).filter(Claim.document_id == document.id).count()
        if count <= 0:
            raise AppException(status_code=422, code=ErrorCode.CLAIM_NOT_FOUND, field="document_id", detail="Document has no extracted claims.", message="Claims missing")

    def _ensure_evidence_packages(self, document: Document, db: Session) -> list[EvidencePackage]:
        packages = db.query(EvidencePackage).filter(EvidencePackage.document_id == document.id).all()
        if packages:
            return packages
        self.evidence_builder.prepare_evidence_for_document(document.id, db)
        return db.query(EvidencePackage).filter(EvidencePackage.document_id == document.id).all()

    def _latest_packages_for_verification(self, document: Document, db: Session) -> list[EvidencePackage]:
        packages = (
            db.query(EvidencePackage)
            .options(selectinload(EvidencePackage.claim), selectinload(EvidencePackage.reference), selectinload(EvidencePackage.citation))
            .filter(EvidencePackage.document_id == document.id)
            .order_by(EvidencePackage.created_at.desc(), EvidencePackage.id.desc())
            .all()
        )
        latest: dict[tuple[str, str], EvidencePackage] = {}
        for package in packages:
            key = (package.claim_id, package.reference_id)
            if key not in latest:
                latest[key] = package
        return list(latest.values())

    def _verify_package(
        self,
        package: EvidencePackage,
        run: PipelineRun,
        steps: dict[str, PipelineStep],
        db: Session,
        *,
        use_cache: bool,
        use_rag: bool,
        request_id: str | None,
        warnings: list[str],
    ) -> VerificationResult:
        claim = db.get(Claim, package.claim_id)
        reference = db.get(Reference, package.reference_id)
        if claim is None or reference is None:
            warnings.append(f"Skipped evidence package {package.id}: claim or reference missing.")
            return self._fallback_result(package, run, db, issue="Claim or reference missing.", rule="MISSING_CLAIM_OR_REFERENCE")

        self._mark_step(steps["CACHE_CHECK"], PipelineStepStatus.RUNNING.value, db, progress=60)
        if use_cache:
            try:
                decision = self.cache_service.check_claim_cache(claim.id, db, reference_id=reference.id, request_id=request_id)
                if decision.get("cache_hit") and decision.get("reusable") and decision.get("matched_result_id"):
                    source = db.get(VerificationResult, decision["matched_result_id"])
                    if source:
                        result = self._create_result_from_cache(source, claim, reference, package, run, db, decision)
                        safety_decision = self.safety_service.evaluate_and_apply(result, db, evidence_package=package, retrieval=None, request_id=request_id)
                        self._mark_step(steps["BASIC_SAFETY_CHECK"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata=safety_decision.to_dict())
                        self._mark_step(steps["CACHE_CHECK"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata={"cache_source": result.cache_source})
                        return result
            except Exception as exc:  # cache failure should not kill verification
                warnings.append(f"Cache check failed for claim {claim.id}: {exc}")
        self._mark_step(steps["CACHE_CHECK"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata={"cache_source": CacheSource.NEW_VERIFICATION.value})

        preliminary = self._pre_rag_safety(package, reference)
        if preliminary:
            return self._fallback_result(package, run, db, issue=preliminary["issue"], rule=preliminary["rule"], status=preliminary["status"])

        if not use_rag:
            return self._fallback_result(package, run, db, issue="RAG retrieval disabled for this pipeline run.", rule="RAG_DISABLED")

        self._mark_step(steps["RAG_RETRIEVAL"], PipelineStepStatus.RUNNING.value, db, progress=70)
        retrieval_data = self.rag_service.retrieve_evidence_for_claim(claim.id, db, reference_id=reference.id, evidence_package_id=package.id, use_mock=None, request_id=request_id)
        retrieval = db.get(RagRetrievalResult, retrieval_data.get("retrieval_result_id")) if retrieval_data.get("retrieval_result_id") else None
        self._mark_step(steps["RAG_RETRIEVAL"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata={"retrieval_status": retrieval_data.get("retrieval_status")})

        no_chunks = retrieval is None or retrieval.retrieval_status != RetrievalStatus.SUCCEEDED.value or not retrieval.top_chunks_json

        # (f) METADATA_ONLY: Door 1 was intentionally skipped — go directly to Door 2
        #     with metadata but no retrieved chunks so the GenAI can still render a
        #     verdict (typically INSUFFICIENT_EVIDENCE) rather than a bare fallback.
        if no_chunks and package.evidence_availability != EvidenceAvailability.METADATA_ONLY.value:
            return self._fallback_result(package, run, db, issue="RAG retrieval did not return relevant evidence.", rule="NO_RELEVANT_EVIDENCE", status=SupportStatus.INSUFFICIENT_EVIDENCE.value, retrieval=retrieval)

        if not no_chunks and (retrieval.overall_similarity_score or 0.0) < self.settings.rag_min_similarity_threshold:
            return self._fallback_result(package, run, db, issue="Overall RAG similarity is below the configured threshold.", rule="LOW_RAG_SIMILARITY", retrieval=retrieval)

        self._mark_step(steps["GENAI_VERIFICATION"], PipelineStepStatus.RUNNING.value, db, progress=80)
        retrieved_chunks = list(retrieval.top_chunks_json or []) if retrieval else []
        overall_sim = retrieval.overall_similarity_score if retrieval else 0.0
        genai_request = self.genai_service.build_request(
            claim_id=claim.id,
            claim_text=claim.claim_text,
            citation_text=package.citation_text,
            doi_status=package.doi_status,
            metadata=package.metadata_json,
            retrieved_evidence=retrieved_chunks,
            overall_similarity_score=overall_sim,
        )
        try:
            validated, genai_result = self.genai_service.verify(genai_request)
            self._store_prompt_run(run, claim, genai_request, validated, True, db, error=None, token_usage=genai_result.token_usage)
        except Exception as exc:
            self._store_prompt_run(run, claim, genai_request, {"error": str(exc)}, False, db, error=str(exc), token_usage=None)
            self._mark_step(steps["GENAI_VERIFICATION"], PipelineStepStatus.PARTIAL_FAILED.value, db, progress=100, error=str(exc))
            return self._fallback_result(package, run, db, issue="GenAI verification output was invalid or unavailable.", rule="GENAI_INVALID_OR_UNAVAILABLE", retrieval=retrieval)
        self._mark_step(steps["GENAI_VERIFICATION"], PipelineStepStatus.SUCCEEDED.value, db, progress=100)

        result = self._store_verification_result(package, run, db, validated=validated, retrieval=retrieval, method="RAG_PLUS_GENAI", cache_source=CacheSource.NEW_VERIFICATION.value)
        safety_decision = self.safety_service.evaluate_and_apply(result, db, evidence_package=package, retrieval=retrieval, request_id=request_id)
        self._mark_step(steps["BASIC_SAFETY_CHECK"], PipelineStepStatus.SUCCEEDED.value, db, progress=100, metadata=safety_decision.to_dict())
        try:
            self.cache_service.index_verification_result(result.id, db, cache_source=CacheSource.NEW_VERIFICATION.value, commit=False)
        except Exception as exc:
            warnings.append(f"Cache indexing skipped for result {result.id}: {exc}")
        db.flush()
        return result

    def _pre_rag_safety(self, package: EvidencePackage, reference: Reference) -> dict[str, str] | None:
        if package.doi_status in {DoiStatus.MISSING.value, DoiStatus.MALFORMED.value, DoiStatus.INVALID.value} or reference.doi_status in {DoiStatus.MISSING.value, DoiStatus.MALFORMED.value, DoiStatus.INVALID.value}:
            return {"issue": "Missing, malformed, or invalid DOI requires human review.", "rule": "DOI_NOT_VALID", "status": SupportStatus.NEEDS_HUMAN_REVIEW.value}
        if package.evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value:
            return {"issue": "No source evidence is available for this claim-reference pair.", "rule": "SOURCE_UNAVAILABLE", "status": SupportStatus.INSUFFICIENT_EVIDENCE.value}
        return None

    def _apply_basic_safety(self, validated: dict[str, Any], package: EvidencePackage, retrieval: RagRetrievalResult) -> dict[str, Any]:
        safety: dict[str, Any] | None = None
        result = dict(validated)
        if (retrieval.overall_similarity_score or 0.0) < self.settings.rag_min_similarity_threshold:
            result.update({"support_status": SupportStatus.NEEDS_HUMAN_REVIEW.value, "human_review_required": True})
            safety = {"issue": "Low RAG similarity triggered human review.", "rule": "LOW_RAG_SIMILARITY", "risk_level": SafetyRiskLevel.MEDIUM.value}
        elif result["confidence"] < 0.60:
            result.update({"support_status": SupportStatus.NEEDS_HUMAN_REVIEW.value, "human_review_required": True})
            safety = {"issue": "GenAI confidence below 0.60 triggered human review.", "rule": "LOW_GENAI_CONFIDENCE", "risk_level": SafetyRiskLevel.MEDIUM.value}
        elif result["support_status"] == SupportStatus.SUPPORTED.value and (retrieval.overall_similarity_score or 0.0) < 0.70:
            result.update({"support_status": SupportStatus.NEEDS_HUMAN_REVIEW.value, "human_review_required": True})
            safety = {"issue": "Supported GenAI result with weak retrieval similarity was downgraded.", "rule": "SUPPORTED_WITH_LOW_SIMILARITY", "risk_level": SafetyRiskLevel.HIGH.value}
        return {"result": result, "safety": safety}

    def _store_verification_result(self, package: EvidencePackage, run: PipelineRun, db: Session, *, validated: dict[str, Any], retrieval: RagRetrievalResult | None, method: str, cache_source: str, source_result_id: str | None = None) -> VerificationResult:
        result = VerificationResult(
            document_id=package.document_id,
            claim_id=package.claim_id,
            reference_id=package.reference_id,
            support_status=validated["support_status"],
            confidence=validated.get("confidence"),
            explanation=validated.get("explanation"),
            limitations=validated.get("limitations"),
            human_review_required=bool(validated.get("human_review_required")),
            evidence_used_json=validated.get("evidence_used") or [],
            evidence_availability=package.evidence_availability,
            evidence_used_count=len(validated.get("evidence_used") or []),
            overall_similarity_score=retrieval.overall_similarity_score if retrieval else None,
            verification_method=method,
            cache_source=cache_source,
            source_result_id=source_result_id,
        )
        # dynamic attribute not persisted, but preserved in in-memory response where needed
        db.add(result)
        db.flush()
        return result

    def _fallback_result(self, package: EvidencePackage, run: PipelineRun, db: Session, *, issue: str, rule: str, status: str = SupportStatus.NEEDS_HUMAN_REVIEW.value, retrieval: RagRetrievalResult | None = None) -> VerificationResult:
        validated = {
            "support_status": status,
            "confidence": 0.0 if status == SupportStatus.NEEDS_HUMAN_REVIEW.value else 0.25,
            "explanation": issue,
            "limitations": "Fallback result generated by BE-10 basic safety gating.",
            "human_review_required": True,
            "evidence_used": [],
        }
        result = self._store_verification_result(package, run, db, validated=validated, retrieval=retrieval, method="FALLBACK_NEEDS_REVIEW", cache_source=CacheSource.NEW_VERIFICATION.value)
        extra = SafetyRuleHit(
            rule=rule,
            issue=issue,
            recommended_action="Human reviewer should inspect this result before relying on it.",
            risk_level=SafetyRiskLevel.HIGH.value,
            final_support_status=status,
            confidence_cap=validated["confidence"],
        )
        self.safety_service.evaluate_and_apply(result, db, evidence_package=package, retrieval=retrieval, extra_rule=extra)
        db.flush()
        return result

    def _create_result_from_cache(self, source: VerificationResult, claim: Claim, reference: Reference, package: EvidencePackage, run: PipelineRun, db: Session, decision: dict[str, Any]) -> VerificationResult:
        validated = {
            "support_status": source.support_status,
            "confidence": source.confidence,
            "explanation": f"Reused cached verification result {source.id}. {source.explanation or ''}".strip(),
            "limitations": source.limitations,
            "human_review_required": source.human_review_required,
            "evidence_used": source.evidence_used_json or [],
        }
        return self._store_verification_result(package, run, db, validated=validated, retrieval=None, method="CACHE_ONLY", cache_source=decision.get("cache_source") or CacheSource.EXACT_CACHE.value, source_result_id=source.id)

    def _store_safety_check(self, result: VerificationResult, db: Session, safety: dict[str, Any]) -> None:
        db.add(
            SafetyCheck(
                verification_result_id=result.id,
                safety_status="TRIGGERED",
                risk_level=safety.get("risk_level") or SafetyRiskLevel.UNKNOWN.value,
                issue=safety.get("issue"),
                recommended_action="NEEDS_HUMAN_REVIEW",
                backend_rule_triggered=safety.get("rule"),
            )
        )
        db.flush()

    def _store_prompt_run(self, run: PipelineRun, claim: Claim, input_payload: dict[str, Any], output_payload: dict[str, Any], success: bool, db: Session, *, error: str | None, token_usage: dict[str, Any] | None) -> None:
        db.add(
            PromptRun(
                document_id=run.document_id,
                claim_id=claim.id,
                pipeline_run_id=run.id,
                prompt_type="CLAIM_VERIFICATION",
                model_provider=self.settings.genai_provider,
                model_name=self.settings.groq_model,
                prompt_version=self.settings.verification_prompt_version,
                input_summary={
                    "claim_id": claim.id,
                    "claim_preview": claim.claim_text[:240],
                    "evidence_chunk_count": len(input_payload.get("retrieved_evidence") or []),
                }.__repr__(),
                output_json=output_payload,
                success=success,
                error_message=error,
                token_usage_json=token_usage,
            )
        )
        db.flush()

    def result_to_dict(self, result: VerificationResult, *, include_details: bool) -> dict[str, Any]:
        claim = result.claim
        reference = result.reference
        safety_checks = list(result.safety_checks or [])
        safety = max(safety_checks, key=lambda item: {"LOW": 0, "UNKNOWN": 0, "MEDIUM": 1, "HIGH": 2}.get(item.risk_level, 0)) if safety_checks else None
        citation_text = None
        try:
            link = claim.reference_links[0] if claim and claim.reference_links else None
            citation_text = link.citation.raw_citation if link and link.citation else None
        except Exception:
            citation_text = None
        data = {
            "result_id": result.id,
            "document_id": result.document_id,
            "claim_id": result.claim_id,
            "reference_id": result.reference_id,
            "claim_text": claim.claim_text if claim else None,
            "citation_text": citation_text,
            "reference_title": reference.extracted_title if reference else None,
            "doi": reference.extracted_doi if reference else None,
            "doi_status": reference.doi_status if reference else None,
            "support_status": result.support_status,
            "confidence": result.confidence,
            "human_review_required": result.human_review_required,
            "cache_source": result.cache_source,
            "evidence_availability": result.evidence_availability,
            "evidence_used_count": result.evidence_used_count,
            "overall_similarity_score": result.overall_similarity_score,
            "verification_method": result.verification_method,
            "explanation": result.explanation,
            "limitations": result.limitations,
            "safety_risk_level": safety.risk_level if safety else SafetyRiskLevel.LOW.value,
            "safety_status": safety.safety_status if safety else "PASS",
            "safety_rules_triggered": [check.backend_rule_triggered for check in safety_checks if check.backend_rule_triggered],
        }
        if include_details:
            retrievals = []
            for retrieval in (claim.retrieval_results if claim else []):
                if retrieval.reference_id == result.reference_id:
                    retrievals.append({"retrieval_result_id": retrieval.id, "top_chunks": retrieval.top_chunks_json or [], "overall_similarity_score": retrieval.overall_similarity_score, "retrieval_confidence": retrieval.retrieval_confidence})
            data["retrieved_evidence"] = retrievals[:3]
            data["verification"] = {"support_status": result.support_status, "confidence": result.confidence, "explanation": result.explanation, "limitations": result.limitations, "human_review_required": result.human_review_required, "cache_source": result.cache_source}
            data["safety_check"] = {"status": safety.safety_status, "risk_level": safety.risk_level, "reason": safety.issue, "recommended_action": safety.recommended_action, "triggered_rule": safety.backend_rule_triggered} if safety else None
            data["safety_checks"] = [
                {
                    "safety_check_id": check.id,
                    "status": check.safety_status,
                    "risk_level": check.risk_level,
                    "reason": check.issue,
                    "recommended_action": check.recommended_action,
                    "triggered_rule": check.backend_rule_triggered,
                }
                for check in safety_checks
            ]
        return data

    def _summary(self, results: list[VerificationResult], total_claims: int) -> dict[str, Any]:
        return {
            "total_claims": total_claims,
            "verification_results": len(results),
            "supported": sum(1 for item in results if item.support_status == SupportStatus.SUPPORTED.value),
            "partially_supported": sum(1 for item in results if item.support_status == SupportStatus.PARTIALLY_SUPPORTED.value),
            "not_supported": sum(1 for item in results if item.support_status == SupportStatus.NOT_SUPPORTED.value),
            "insufficient_evidence": sum(1 for item in results if item.support_status == SupportStatus.INSUFFICIENT_EVIDENCE.value),
            "needs_human_review": sum(1 for item in results if item.support_status == SupportStatus.NEEDS_HUMAN_REVIEW.value),
        }
