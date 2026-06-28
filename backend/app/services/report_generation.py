
from __future__ import annotations

import html
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppException, ErrorCode
from app.models import (
    ClaimReferenceLink,
    Document,
    Reference,
    Report,
    SafetyCheck,
    UatSurvey,
    UserFeedback,
    VerificationResult,
)
from app.models.enums import (
    CacheSource,
    DoiStatus,
    EvidenceAvailability,
    MetadataStatus,
    SafetyRiskLevel,
    SupportStatus,
)

logger = logging.getLogger(__name__)

ALLOWED_SUPPORT_LABELS = {item.value for item in SupportStatus}
ALLOWED_FEEDBACK_TYPES = {"WRONG_MAPPING", "MISSING_REFERENCE", "WRONG_VERDICT", "UNCLEAR_EXPLANATION", "OTHER"}
RISK_ORDER = {SafetyRiskLevel.LOW.value: 0, SafetyRiskLevel.UNKNOWN.value: 0, SafetyRiskLevel.MEDIUM.value: 1, SafetyRiskLevel.HIGH.value: 2}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(value)


def _safe(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


class DocumentSummaryService:
    """Deterministic BE-12 summary builder from stored backend data."""

    def get_document_summary(self, document_id: str, db: Session) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(
                status_code=404,
                code=ErrorCode.DOCUMENT_NOT_FOUND,
                field="document_id",
                detail="Document was not found.",
                message="Document not found",
            )
        references = list(db.scalars(select(Reference).where(Reference.document_id == document.id)).all())
        results = self._latest_results(document.id, db)
        safety_checks = self._safety_checks_for_results([result.id for result in results], db)
        reports_count = db.query(Report).filter(Report.document_id == document.id, Report.status == "GENERATED").count()
        doi_summary = self._doi_summary(references)
        verification_summary = self._verification_summary(results, safety_checks)
        risk = self._risk_summary(results, safety_checks)
        return {
            "document_id": document.id,
            "filename": document.filename,
            "title": document.title,
            "status": document.status,
            "pages_count": document.pages_count,
            "latest_pipeline_run_id": document.latest_pipeline_run_id,
            "total_references": len(references),
            **doi_summary,
            "total_claims": document.claims_count,
            **verification_summary,
            **risk,
            "report_ready": bool(results),
            "reports_count": reports_count,
            "phase": "BE-12",
        }

    def _latest_results(self, document_id: str, db: Session) -> list[VerificationResult]:
        statement = (
            select(VerificationResult)
            .options(
                selectinload(VerificationResult.claim),
                selectinload(VerificationResult.reference),
                selectinload(VerificationResult.safety_checks),
            )
            .where(VerificationResult.document_id == document_id)
            .order_by(VerificationResult.created_at.desc(), VerificationResult.id.desc())
        )
        all_results = list(db.scalars(statement).all())
        latest: dict[tuple[str, str], VerificationResult] = {}
        for result in all_results:
            key = (result.claim_id, result.reference_id)
            if key not in latest:
                latest[key] = result
        return list(latest.values())

    def _safety_checks_for_results(self, result_ids: list[str], db: Session) -> list[SafetyCheck]:
        if not result_ids:
            return []
        return list(db.scalars(select(SafetyCheck).where(SafetyCheck.verification_result_id.in_(result_ids))).all())

    def _doi_summary(self, references: list[Reference]) -> dict[str, Any]:
        doi_counts = Counter(ref.doi_status for ref in references)
        metadata_counts = Counter(ref.metadata_status for ref in references)
        scores = [ref.metadata_match_score for ref in references if ref.metadata_match_score is not None]
        return {
            "valid_dois": doi_counts.get(DoiStatus.VALID.value, 0),
            "missing_dois": doi_counts.get(DoiStatus.MISSING.value, 0),
            "malformed_dois": doi_counts.get(DoiStatus.MALFORMED.value, 0),
            "invalid_dois": doi_counts.get(DoiStatus.INVALID.value, 0),
            "lookup_failed": metadata_counts.get(MetadataStatus.LOOKUP_FAILED.value, 0),
            "metadata_lookup_succeeded": metadata_counts.get(MetadataStatus.LOOKUP_SUCCEEDED.value, 0),
            "metadata_unavailable": metadata_counts.get(MetadataStatus.METADATA_UNAVAILABLE.value, 0),
            "average_metadata_match_score": round(mean(scores), 3) if scores else None,
        }

    def _verification_summary(self, results: list[VerificationResult], safety_checks: list[SafetyCheck]) -> dict[str, Any]:
        support_counts = Counter(result.support_status for result in results)
        cache_counts = Counter(result.cache_source for result in results)
        evidence_counts = Counter(result.evidence_availability for result in results)
        confidences = [result.confidence for result in results if result.confidence is not None]
        low_similarity = sum(1 for result in results if result.overall_similarity_score is not None and result.overall_similarity_score < 0.60)
        return {
            "verification_results": len(results),
            "supported": support_counts.get(SupportStatus.SUPPORTED.value, 0),
            "partially_supported": support_counts.get(SupportStatus.PARTIALLY_SUPPORTED.value, 0),
            "not_supported": support_counts.get(SupportStatus.NOT_SUPPORTED.value, 0),
            "insufficient_evidence": support_counts.get(SupportStatus.INSUFFICIENT_EVIDENCE.value, 0),
            "needs_human_review": support_counts.get(SupportStatus.NEEDS_HUMAN_REVIEW.value, 0),
            "cache_new_verification": cache_counts.get(CacheSource.NEW_VERIFICATION.value, 0),
            "cache_exact": cache_counts.get(CacheSource.EXACT_CACHE.value, 0),
            "cache_semantic": cache_counts.get(CacheSource.SEMANTIC_CACHE.value, 0),
            "cache_human_corrected": cache_counts.get(CacheSource.HUMAN_CORRECTED.value, 0),
            "average_confidence": round(mean(confidences), 3) if confidences else None,
            "human_review_required_count": sum(1 for result in results if result.human_review_required),
            "low_similarity_count": low_similarity,
            "source_unavailable_count": evidence_counts.get(EvidenceAvailability.SOURCE_UNAVAILABLE.value, 0),
            "metadata_only_count": evidence_counts.get(EvidenceAvailability.METADATA_ONLY.value, 0),
            "abstract_available_count": evidence_counts.get(EvidenceAvailability.ABSTRACT_AVAILABLE.value, 0),
            "full_text_available_count": evidence_counts.get(EvidenceAvailability.FULL_TEXT_AVAILABLE.value, 0),
            "safety_checks_count": len(safety_checks),
        }

    def _risk_summary(self, results: list[VerificationResult], safety_checks: list[SafetyCheck]) -> dict[str, Any]:
        by_result: dict[str, list[SafetyCheck]] = defaultdict(list)
        for check in safety_checks:
            by_result[check.verification_result_id].append(check)
        high = 0
        medium = 0
        low = 0
        for result in results:
            checks = by_result.get(result.id, [])
            if checks:
                risk = max((check.risk_level for check in checks), key=lambda item: RISK_ORDER.get(item, 0))
            elif result.human_review_required:
                risk = SafetyRiskLevel.MEDIUM.value
            else:
                risk = SafetyRiskLevel.LOW.value
            if risk == SafetyRiskLevel.HIGH.value:
                high += 1
            elif risk == SafetyRiskLevel.MEDIUM.value:
                medium += 1
            else:
                low += 1
        review_ratio = (sum(1 for result in results if result.human_review_required) / len(results)) if results else 0.0
        overall = SafetyRiskLevel.LOW.value
        if high > 0 or review_ratio >= 0.50:
            overall = SafetyRiskLevel.HIGH.value
        elif medium > 0 or review_ratio >= 0.20:
            overall = SafetyRiskLevel.MEDIUM.value
        return {
            "high_risk_count": high,
            "medium_risk_count": medium,
            "low_risk_count": low,
            "overall_risk_level": overall,
        }


class ReportService:
    """BE-12 HTML report generation and retrieval."""

    def __init__(self) -> None:
        self.summary_service = DocumentSummaryService()

    def generate_report(
        self,
        document_id: str,
        db: Session,
        *,
        report_format: str = "HTML",
        include_evidence_chunks: bool = True,
        include_human_review_items: bool = True,
        include_limitations: bool = True,
    ) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document was not found.", message="Document not found")
        if report_format.upper() != "HTML":
            raise AppException(status_code=422, code=ErrorCode.REPORT_EXPORT_NOT_SUPPORTED, field="format", detail="Only HTML report generation is supported in BE-12.", message="Report export not supported")

        results = self.summary_service._latest_results(document.id, db)
        if not results:
            raise AppException(
                status_code=422,
                code=ErrorCode.VERIFICATION_NOT_COMPLETED,
                field="document_id",
                detail="Verification must be completed before generating a report.",
                message="Verification not completed",
            )
        summary = self.summary_service.get_document_summary(document.id, db)
        high_risk_items = self._high_risk_items(results, db)
        detailed_results = [self._result_row(result) for result in results]
        html_content = self._render_html_report(
            document=document,
            summary=summary,
            high_risk_items=high_risk_items,
            detailed_results=detailed_results,
            include_human_review_items=include_human_review_items,
            include_limitations=include_limitations,
        )
        report = Report(
            document_id=document.id,
            format="HTML",
            status="GENERATED",
            title=f"RefCheck Verification Report — {document.title or document.filename}",
            html_content=html_content,
            summary_json={
                "summary": summary,
                "high_risk_items_count": len(high_risk_items),
                "generated_at": _iso(_utc_now()),
                "limitations_included": include_limitations,
                "evidence_chunks_included": include_evidence_chunks,
            },
        )
        db.add(report)
        db.flush()
        logger.info("be12_report_generated", extra={"document_id": document.id, "report_id": report.id, "results": len(results)})
        db.commit()
        return {
            "report_id": report.id,
            "document_id": document.id,
            "format": report.format,
            "status": report.status,
            "title": report.title,
            "report_url": f"/api/v1/reports/{report.id}",
            "summary": summary,
            "created_at": _iso(report.created_at),
        }

    def get_report(self, report_id: str, db: Session) -> dict[str, Any]:
        report = db.get(Report, report_id)
        if report is None:
            raise AppException(status_code=404, code=ErrorCode.REPORT_NOT_FOUND, field="report_id", detail="Report was not found.", message="Report not found")
        return self._report_to_dict(report)

    def get_latest_report_for_document(self, document_id: str, db: Session) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document was not found.", message="Document not found")
        report = (
            db.query(Report)
            .filter(Report.document_id == document.id, Report.status == "GENERATED")
            .order_by(Report.created_at.desc(), Report.id.desc())
            .first()
        )
        if report is None:
            raise AppException(status_code=404, code=ErrorCode.REPORT_NOT_FOUND, field="document_id", detail="No generated report was found for this document.", message="Report not found")
        return self._report_to_dict(report)

    def download_report(self, report_id: str, report_format: str, db: Session) -> dict[str, Any]:
        if report_format.upper() != "HTML":
            raise AppException(status_code=422, code=ErrorCode.REPORT_EXPORT_NOT_SUPPORTED, field="format", detail="PDF export is not implemented in BE-12. Use the HTML report content.", message="Report export not supported")
        return self.get_report(report_id, db)

    def _report_to_dict(self, report: Report) -> dict[str, Any]:
        return {
            "report_id": report.id,
            "document_id": report.document_id,
            "title": report.title,
            "format": report.format,
            "status": report.status,
            "summary": report.summary_json,
            "html_content": report.html_content,
            "created_at": _iso(report.created_at),
            "updated_at": _iso(report.updated_at),
            "phase": "BE-12",
        }

    def _high_risk_items(self, results: list[VerificationResult], db: Session) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in results:
            checks = sorted(result.safety_checks or [], key=lambda item: RISK_ORDER.get(item.risk_level, 0), reverse=True)
            top_check = checks[0] if checks else None
            is_high_risk = (
                result.human_review_required
                or result.support_status in {SupportStatus.NEEDS_HUMAN_REVIEW.value, SupportStatus.INSUFFICIENT_EVIDENCE.value}
                or (top_check and top_check.risk_level == SafetyRiskLevel.HIGH.value)
                or result.evidence_availability == EvidenceAvailability.SOURCE_UNAVAILABLE.value
                or (result.overall_similarity_score is not None and result.overall_similarity_score < 0.60)
            )
            if is_high_risk:
                items.append({
                    "claim_id": result.claim_id,
                    "claim_text": result.claim.claim_text if result.claim else None,
                    "citation_text": self._citation_text(result),
                    "reference_title": result.reference.extracted_title if result.reference else None,
                    "doi": result.reference.extracted_doi if result.reference else None,
                    "support_status": result.support_status,
                    "confidence": result.confidence,
                    "safety_risk_level": top_check.risk_level if top_check else (SafetyRiskLevel.MEDIUM.value if result.human_review_required else SafetyRiskLevel.LOW.value),
                    "reason": top_check.issue if top_check else result.limitations,
                    "recommended_action": top_check.recommended_action if top_check else "Human reviewer should inspect this result.",
                })
        return items

    def _result_row(self, result: VerificationResult) -> dict[str, Any]:
        top_check = None
        checks = list(result.safety_checks or [])
        if checks:
            top_check = max(checks, key=lambda item: RISK_ORDER.get(item.risk_level, 0))
        return {
            "result_id": result.id,
            "claim_id": result.claim_id,
            "claim_text": result.claim.claim_text if result.claim else None,
            "citation_text": self._citation_text(result),
            "reference_title": result.reference.extracted_title if result.reference else None,
            "doi": result.reference.extracted_doi if result.reference else None,
            "doi_status": result.reference.doi_status if result.reference else None,
            "support_status": result.support_status,
            "confidence": result.confidence,
            "evidence_availability": result.evidence_availability,
            "overall_similarity_score": result.overall_similarity_score,
            "human_review_required": result.human_review_required,
            "explanation": result.explanation,
            "limitations": result.limitations,
            "safety_reason": top_check.issue if top_check else None,
            "safety_risk_level": top_check.risk_level if top_check else SafetyRiskLevel.LOW.value,
        }

    def _citation_text(self, result: VerificationResult) -> str | None:
        try:
            links = result.claim.reference_links if result.claim else []
            for link in links:
                if link.reference_id == result.reference_id and link.citation:
                    return link.citation.raw_citation
            if links and links[0].citation:
                return links[0].citation.raw_citation
        except Exception:
            return None
        return None

    def _render_html_report(
        self,
        *,
        document: Document,
        summary: dict[str, Any],
        high_risk_items: list[dict[str, Any]],
        detailed_results: list[dict[str, Any]],
        include_human_review_items: bool,
        include_limitations: bool,
    ) -> str:
        status_rows = "".join(
            f"<tr><td>{_safe(row['support_status'])}</td><td>{_safe(row['claim_text'])}</td><td>{_safe(row['citation_text'])}</td><td>{_safe(row['reference_title'])}</td><td>{_safe(row['doi'])}</td><td>{_safe(row['confidence'])}</td><td>{_safe(row['human_review_required'])}</td><td>{_safe(row['safety_reason'])}</td></tr>"
            for row in detailed_results
        )
        high_risk_html = ""
        if include_human_review_items:
            risk_rows = "".join(
                f"<li><strong>{_safe(item['support_status'])}</strong>: {_safe(item['claim_text'])}<br><em>Reason:</em> {_safe(item['reason'])}<br><em>Action:</em> {_safe(item['recommended_action'])}</li>"
                for item in high_risk_items
            ) or "<li>No high-risk claim items were detected.</li>"
            high_risk_html = f"<section><h2>High-risk / Human-review Claims</h2><ul>{risk_rows}</ul></section>"
        limitations = ""
        if include_limitations:
            limitations = """
            <section>
              <h2>Limitations</h2>
              <ul>
                <li>This report evaluates evidence support for cited claims; it does not prove absolute scientific truth.</li>
                <li>DOI metadata confirms source identity/availability but does not prove claim support by itself.</li>
                <li>Abstract-only or metadata-only evidence may be insufficient for detailed scientific claims.</li>
                <li>Missing DOI, unavailable metadata, weak similarity, or safety warnings require human review.</li>
                <li>GenAI outputs are backend-validated and safety-checked, but they do not replace academic judgment.</li>
                <li>Full-text availability depends on source access and licensing; BE-12 does not scrape publishers.</li>
              </ul>
            </section>
            """
        generated = _safe(_iso(_utc_now()))
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_safe(document.title or document.filename)} — RefCheck Verification Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #17202a; line-height: 1.45; }}
h1, h2 {{ color: #1f4e5f; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }}
.card {{ border: 1px solid #d5dde2; border-radius: 8px; padding: 12px; background: #f8fbfc; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d5dde2; padding: 8px; vertical-align: top; }}
th {{ background: #eef5f7; }}
.notice {{ background: #fff8e6; border-left: 4px solid #e0a800; padding: 10px; }}
</style>
</head>
<body>
<h1>RefCheck Scientific Reference Verification Report</h1>
<p><strong>Document:</strong> {_safe(document.title or document.filename)}<br>
<strong>Document ID:</strong> {_safe(document.id)}<br>
<strong>Generated:</strong> {generated}</p>
<p class="notice">This report summarizes backend-stored verification results and safety checks. It is an academic assistance report, not a final proof of scientific truth.</p>
<section>
<h2>Document Overview</h2>
<div class="summary-grid">
<div class="card"><strong>Total references</strong><br>{_safe(summary.get("total_references"))}</div>
<div class="card"><strong>Total claims</strong><br>{_safe(summary.get("total_claims"))}</div>
<div class="card"><strong>Verification results</strong><br>{_safe(summary.get("verification_results"))}</div>
<div class="card"><strong>Overall risk</strong><br>{_safe(summary.get("overall_risk_level"))}</div>
</div>
</section>
<section>
<h2>DOI / Reference Quality Summary</h2>
<div class="summary-grid">
<div class="card"><strong>Valid DOIs</strong><br>{_safe(summary.get("valid_dois"))}</div>
<div class="card"><strong>Missing DOIs</strong><br>{_safe(summary.get("missing_dois"))}</div>
<div class="card"><strong>Malformed DOIs</strong><br>{_safe(summary.get("malformed_dois"))}</div>
<div class="card"><strong>Invalid DOIs</strong><br>{_safe(summary.get("invalid_dois"))}</div>
<div class="card"><strong>Metadata succeeded</strong><br>{_safe(summary.get("metadata_lookup_succeeded"))}</div>
<div class="card"><strong>Metadata unavailable</strong><br>{_safe(summary.get("metadata_unavailable"))}</div>
</div>
</section>
<section>
<h2>Claim Verification Summary</h2>
<div class="summary-grid">
<div class="card"><strong>Supported</strong><br>{_safe(summary.get("supported"))}</div>
<div class="card"><strong>Partially supported</strong><br>{_safe(summary.get("partially_supported"))}</div>
<div class="card"><strong>Not supported</strong><br>{_safe(summary.get("not_supported"))}</div>
<div class="card"><strong>Insufficient evidence</strong><br>{_safe(summary.get("insufficient_evidence"))}</div>
<div class="card"><strong>Needs human review</strong><br>{_safe(summary.get("needs_human_review"))}</div>
<div class="card"><strong>Average confidence</strong><br>{_safe(summary.get("average_confidence"))}</div>
</div>
</section>
{high_risk_html}
<section>
<h2>Detailed Claim Verification Table</h2>
<table>
<thead><tr><th>Status</th><th>Claim</th><th>Citation</th><th>Reference</th><th>DOI</th><th>Confidence</th><th>Human review</th><th>Safety reason</th></tr></thead>
<tbody>{status_rows}</tbody>
</table>
</section>
<section>
<h2>Evidence and Safety Notes</h2>
<p>Counts and risk levels are computed from backend VerificationResult and SafetyCheck records. Human-review recommendations are surfaced when DOI, metadata, evidence availability, similarity, or confidence conditions are weak.</p>
</section>
{limitations}
</body></html>"""


class FeedbackService:
    """BE-12 feedback storage without unsafe automatic corrections."""

    def submit_verification_feedback(
        self,
        result_id: str,
        db: Session,
        *,
        user_label: str | None,
        user_comment: str | None,
        user_role: str | None,
    ) -> dict[str, Any]:
        result = db.get(VerificationResult, result_id)
        if result is None:
            raise AppException(status_code=404, code=ErrorCode.VERIFICATION_RESULT_NOT_FOUND, field="result_id", detail="Verification result was not found.", message="Verification result not found")
        if user_label and user_label not in ALLOWED_SUPPORT_LABELS:
            raise AppException(status_code=422, code=ErrorCode.INVALID_FEEDBACK_LABEL, field="user_label", detail="Feedback label must be one of the allowed support statuses.", message="Invalid feedback label")
        feedback = UserFeedback(
            document_id=result.document_id,
            result_id=result.id,
            feedback_type="VERIFICATION_RESULT",
            user_label=user_label,
            user_comment=user_comment,
            user_role=user_role,
        )
        db.add(feedback)
        db.commit()
        return {
            "feedback_id": feedback.id,
            "document_id": feedback.document_id,
            "result_id": feedback.result_id,
            "feedback_type": feedback.feedback_type,
            "user_label": feedback.user_label,
            "user_role": feedback.user_role,
            "created_at": _iso(feedback.created_at),
            "applied_automatically": False,
        }

    def submit_mapping_feedback(
        self,
        link_id: str,
        db: Session,
        *,
        feedback_type: str,
        suggested_reference_id: str | None,
        comment: str | None,
        user_role: str | None,
    ) -> dict[str, Any]:
        link = db.get(ClaimReferenceLink, link_id)
        if link is None:
            raise AppException(status_code=404, code=ErrorCode.CLAIM_REFERENCE_LINK_NOT_FOUND, field="link_id", detail="Claim-reference link was not found.", message="Claim-reference link not found")
        if feedback_type not in ALLOWED_FEEDBACK_TYPES:
            raise AppException(status_code=422, code=ErrorCode.INVALID_FEEDBACK_LABEL, field="feedback_type", detail="Feedback type is not supported.", message="Invalid feedback type")
        if suggested_reference_id:
            suggested = db.get(Reference, suggested_reference_id)
            if suggested is None or suggested.document_id != link.document_id:
                raise AppException(status_code=422, code=ErrorCode.REFERENCE_NOT_FOUND, field="suggested_reference_id", detail="Suggested reference must exist in the same document.", message="Suggested reference invalid")
        feedback = UserFeedback(
            document_id=link.document_id,
            link_id=link.id,
            feedback_type=feedback_type,
            suggested_reference_id=suggested_reference_id,
            user_comment=comment,
            user_role=user_role,
        )
        db.add(feedback)
        db.commit()
        return {
            "feedback_id": feedback.id,
            "document_id": feedback.document_id,
            "link_id": feedback.link_id,
            "feedback_type": feedback.feedback_type,
            "suggested_reference_id": feedback.suggested_reference_id,
            "user_role": feedback.user_role,
            "created_at": _iso(feedback.created_at),
            "applied_automatically": False,
        }


class UatSurveyService:
    """BE-12 UAT survey storage."""

    def submit_survey(
        self,
        db: Session,
        *,
        document_id: str,
        participant_role: str | None,
        ease_of_use_rating: int,
        result_clarity_rating: int,
        trust_rating: int,
        usefulness_rating: int,
        comments: str | None,
    ) -> dict[str, Any]:
        document = db.get(Document, document_id)
        if document is None:
            raise AppException(status_code=404, code=ErrorCode.DOCUMENT_NOT_FOUND, field="document_id", detail="Document was not found.", message="Document not found")
        for field, value in {
            "ease_of_use_rating": ease_of_use_rating,
            "result_clarity_rating": result_clarity_rating,
            "trust_rating": trust_rating,
            "usefulness_rating": usefulness_rating,
        }.items():
            if value < 1 or value > 5:
                raise AppException(status_code=422, code=ErrorCode.INVALID_RATING, field=field, detail="Ratings must be between 1 and 5.", message="Invalid rating")
        survey = UatSurvey(
            document_id=document.id,
            participant_role=participant_role,
            ease_of_use_rating=ease_of_use_rating,
            result_clarity_rating=result_clarity_rating,
            trust_rating=trust_rating,
            usefulness_rating=usefulness_rating,
            comments=comments,
        )
        db.add(survey)
        db.commit()
        return {
            "survey_id": survey.id,
            "document_id": survey.document_id,
            "participant_role": survey.participant_role,
            "created_at": _iso(survey.created_at),
        }
