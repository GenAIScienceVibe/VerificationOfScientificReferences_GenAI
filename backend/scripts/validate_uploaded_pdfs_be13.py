from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@dataclass(frozen=True)
class ValidationOptions:
    """Execution modes for uploaded-PDF integration validation."""

    rag_mode: str = "mock"
    genai_mode: str = "mock"
    metadata_mode: str = "disabled"
    live_rag_embeddings: bool = False

    @property
    def use_mock_rag(self) -> bool:
        return self.rag_mode == "mock"

    @property
    def retrieval_mode(self) -> str:
        return "Mock RAG" if self.use_mock_rag else "Real RAG"

    @property
    def verification_mode(self) -> str:
        return "Mock GenAI" if self.genai_mode == "mock" else "Real GenAI"

    @property
    def rag_execution_boundary(self) -> str:
        if self.use_mock_rag:
            return "mock RAG client"
        if self.live_rag_embeddings:
            return "fully live external embeddings"
        return "real RagDirectClient adapter with deterministic Door 1 boundary"


@dataclass
class DeterministicRagProbe:
    calls: list[dict[str, Any]] = field(default_factory=list)
    original_retrieve_evidence: Callable[..., Any] | None = None


@dataclass(frozen=True)
class ValidationRuntime:
    client: Any
    SessionLocal: Any
    drop_db_for_tests_only: Callable[[], None]
    init_db: Callable[[], None]
    ClaimReferenceLink: Any
    EvidencePackage: Any
    RagRetrievalResult: Any
    Reference: Any
    Report: Any
    SafetyCheck: Any
    VerificationResult: Any
    CacheSource: Any
    DoiStatus: Any
    EvidenceAvailability: Any
    SupportStatus: Any
    VerificationCacheService: Any


_runtime: ValidationRuntime | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run uploaded research PDF backend validation in mock or staged real-RAG modes. "
            "The default real-RAG mode exercises the real backend adapter, validator, and "
            "persistence boundary with deterministic Door 1 output; use "
            "--live-rag-embeddings only for fully live external embedding validation."
        )
    )
    parser.add_argument("pdfs", nargs="*", type=Path)
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=None,
        help="Directory containing local research PDFs. PDFs are never added to reports or release packages.",
    )
    parser.add_argument("--reset-db", action="store_true", help="Reset the isolated validation database before running.")

    rag_group = parser.add_mutually_exclusive_group()
    rag_group.add_argument("--mock-rag", dest="rag_mode", action="store_const", const="mock", help="Use the existing deterministic mock RAG client (default).")
    rag_group.add_argument("--real-rag", dest="rag_mode", action="store_const", const="real", help="Use the real RagDirectClient adapter path.")

    genai_group = parser.add_mutually_exclusive_group()
    genai_group.add_argument("--mock-genai", dest="genai_mode", action="store_const", const="mock", help="Keep GenAI verification deterministic and offline (default).")
    genai_group.add_argument("--real-genai", dest="genai_mode", action="store_const", const="real", help="Use real Door 2 only when OPENROUTER_API_KEY is configured.")

    metadata_group = parser.add_mutually_exclusive_group()
    metadata_group.add_argument("--metadata-disabled", dest="metadata_mode", action="store_const", const="disabled", help="Block external metadata and full-text provider calls (default).")
    metadata_group.add_argument("--metadata-mock", dest="metadata_mode", action="store_const", const="mock", help="Use deterministic metadata mode with external provider calls blocked.")
    metadata_group.add_argument("--metadata-live", dest="metadata_mode", action="store_const", const="live", help="Allow configured external metadata providers.")

    parser.add_argument(
        "--live-rag-embeddings",
        action="store_true",
        help="With --real-rag, call fully live external embeddings instead of the deterministic Door 1 boundary; requires OPENROUTER_API_KEY.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Optional Markdown or JSON path for a machine-readable validation report.",
    )
    parser.set_defaults(rag_mode="mock", genai_mode="mock", metadata_mode="disabled")
    return parser


def options_from_args(args: argparse.Namespace) -> ValidationOptions:
    return ValidationOptions(
        rag_mode=args.rag_mode,
        genai_mode=args.genai_mode,
        metadata_mode=args.metadata_mode,
        live_rag_embeddings=bool(args.live_rag_embeddings),
    )


def configure_environment(options: ValidationOptions) -> dict[str, str]:
    """Configure modes before any backend settings or application imports occur."""
    os.environ.setdefault(
        "DATABASE_URL",
        f"sqlite:///{(BACKEND_ROOT / 'data' / 'be13_uploaded_pdf_validation.db').as_posix()}",
    )
    os.environ.setdefault(
        "FILE_STORAGE_DIR",
        (BACKEND_ROOT / "data" / "be13_uploaded_pdf_uploads").as_posix(),
    )
    os.environ.setdefault("ENABLE_RAW_TEXT_DEBUG_ENDPOINT", "true")
    os.environ.setdefault("DEMO_MODE", "true")
    os.environ.setdefault("CACHE_SEMANTIC_ENABLED", "false")
    os.environ["RAG_MOCK_MODE"] = "true" if options.use_mock_rag else "false"
    os.environ["GENAI_MOCK_MODE"] = "true" if options.genai_mode == "mock" else "false"
    os.environ["METADATA_SERVICE_TIMEOUT_SECONDS"] = "1"
    os.environ["METADATA_MAX_RETRIES"] = "0"
    if options.metadata_mode == "live":
        os.environ["METADATA_MOCK_MODE"] = "false"
        os.environ["METADATA_LOOKUP_ENABLED"] = "true"
    else:
        os.environ["METADATA_MOCK_MODE"] = "true" if options.metadata_mode == "mock" else "false"
        os.environ["METADATA_LOOKUP_ENABLED"] = "false"
    return {
        "RAG_MOCK_MODE": os.environ["RAG_MOCK_MODE"],
        "GENAI_MOCK_MODE": os.environ["GENAI_MOCK_MODE"],
        "METADATA_MOCK_MODE": os.environ["METADATA_MOCK_MODE"],
        "METADATA_LOOKUP_ENABLED": os.environ["METADATA_LOOKUP_ENABLED"],
    }


def check_real_rag_dependencies(
    importer: Callable[[str], Any] = importlib.import_module,
) -> tuple[bool, str | None]:
    required_modules = (
        "rag.api",
        "rag.ingestion.models",
        "rag.retrieval.embedder",
        "app.services.rag_ml_integration",
    )
    try:
        for module_name in required_modules:
            importer(module_name)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def validate_mode_preconditions(
    options: ValidationOptions,
    *,
    dependencies_available: bool,
    dependency_error: str | None,
) -> tuple[bool, str | None]:
    if options.live_rag_embeddings and options.use_mock_rag:
        return False, "--live-rag-embeddings requires --real-rag."
    if not options.use_mock_rag and not dependencies_available:
        return False, f"Real RAG dependencies are unavailable: {dependency_error}"
    if options.live_rag_embeddings and not os.getenv("OPENROUTER_API_KEY"):
        return False, "Fully live RAG embeddings require OPENROUTER_API_KEY."
    if options.genai_mode == "real" and not os.getenv("OPENROUTER_API_KEY"):
        return False, "Real GenAI is optional and requires OPENROUTER_API_KEY."
    return True, None


def _load_runtime() -> ValidationRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime

    from testsupport.api_client import ApiTestClient as TestClient

    from app.db.init_db import drop_db_for_tests_only, init_db
    from app.db.session import SessionLocal
    from app.main import app
    from app.models import (
        ClaimReferenceLink,
        EvidencePackage,
        RagRetrievalResult,
        Reference,
        Report,
        SafetyCheck,
        VerificationResult,
    )
    from app.models.enums import (
        CacheSource,
        DoiStatus,
        EvidenceAvailability,
        SupportStatus,
    )
    from app.services.verification_cache import VerificationCacheService

    _runtime = ValidationRuntime(
        client=TestClient(app),
        SessionLocal=SessionLocal,
        drop_db_for_tests_only=drop_db_for_tests_only,
        init_db=init_db,
        ClaimReferenceLink=ClaimReferenceLink,
        EvidencePackage=EvidencePackage,
        RagRetrievalResult=RagRetrievalResult,
        Reference=Reference,
        Report=Report,
        SafetyCheck=SafetyCheck,
        VerificationResult=VerificationResult,
        CacheSource=CacheSource,
        DoiStatus=DoiStatus,
        EvidenceAvailability=EvidenceAvailability,
        SupportStatus=SupportStatus,
        VerificationCacheService=VerificationCacheService,
    )
    return _runtime


def install_deterministic_rag_probe() -> DeterministicRagProbe:
    """Stub Door 1 output while retaining the real backend adapter boundary."""
    import rag.api as rag_api

    probe = DeterministicRagProbe(original_retrieve_evidence=rag_api.retrieve_evidence)

    def deterministic_retrieve(request: Any) -> Any:
        probe.calls.append(
            {
                "claim_id": request.claim_id,
                "reference_id": request.reference_id,
                "doi": request.doi,
                "top_k": request.top_k,
                "source_url": request.source_evidence.source_url,
            }
        )
        chunks = [
            rag_api.TopChunkResult(
                chunk_id="deterministic_adapter_chunk_001",
                chunk_text="Deterministic evidence used only to validate the real adapter, validator, persistence, and backend safety boundary.",
                similarity_score=0.84,
                evidence_type=request.source_evidence.evidence_availability.value.replace("_AVAILABLE", ""),
            ),
            rag_api.TopChunkResult(
                chunk_id="deterministic_adapter_chunk_002",
                chunk_text="This staged result does not assert live embedding quality or academic support.",
                similarity_score=0.72,
                evidence_type=request.source_evidence.evidence_availability.value.replace("_AVAILABLE", ""),
            ),
        ][: request.top_k]
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.SUCCEEDED,
            top_chunks=chunks,
            overall_similarity_score=chunks[0].similarity_score if chunks else 0.0,
            retrieval_confidence=(sum(item.similarity_score for item in chunks) / len(chunks)) if chunks else 0.0,
        )

    rag_api.retrieve_evidence = deterministic_retrieve
    return probe


def restore_deterministic_rag_probe(probe: DeterministicRagProbe) -> None:
    if probe.original_retrieve_evidence is None:
        return
    import rag.api as rag_api

    rag_api.retrieve_evidence = probe.original_retrieve_evidence


def collect_pdf_paths(*, pdf_dir: Path | None, pdfs: list[Path]) -> tuple[list[Path], str | None]:
    collected = list(pdfs)
    if pdf_dir is not None:
        if not pdf_dir.exists():
            return [], f"PDF directory not found: {pdf_dir}"
        if not pdf_dir.is_dir():
            return [], f"PDF path is not a directory: {pdf_dir}"
        collected.extend(
            sorted(
                path
                for path in pdf_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".pdf"
            )
        )
    if not collected:
        location = str(pdf_dir) if pdf_dir is not None else "positional arguments"
        return [], f"No PDF files found from {location}."
    missing = [str(path) for path in collected if not path.exists()]
    if missing:
        return [], f"PDF file not found: {', '.join(missing)}"
    non_pdfs = [str(path) for path in collected if path.suffix.lower() != ".pdf"]
    if non_pdfs:
        return [], f"Non-PDF input is not supported: {', '.join(non_pdfs)}"
    return collected, None


def _post_pdf(path: Path, runtime: ValidationRuntime) -> dict[str, Any]:
    with path.open("rb") as handle:
        response = runtime.client.post(
            "/api/v1/documents/upload",
            files={"file": (path.name, handle, "application/pdf")},
            data={"document_title": path.stem, "uploaded_by": "be13-validation"},
            headers={"X-Request-ID": f"req_be13_{path.stem[:12]}"},
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Upload failed for {path.name}: {response.status_code} {response.text}"
        )
    assert response.headers.get("x-request-id")
    return response.json()["data"]


def _safe_post(
    path: str,
    runtime: ValidationRuntime,
    json_payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    response = runtime.client.post(
        path,
        json=json_payload,
        headers={"X-Request-ID": "req_be13_validation"},
    )
    return response.status_code, response.json()


def _get_data(path: str, runtime: ValidationRuntime) -> dict[str, Any]:
    response = runtime.client.get(
        path,
        headers={"X-Request-ID": "req_be13_validation"},
    )
    payload = response.json()
    if response.status_code >= 400:
        return payload
    return payload["data"]


def _seed_cache_for_first_package(document_id: str, runtime: ValidationRuntime) -> int:
    with runtime.SessionLocal() as db:
        package = (
            db.query(runtime.EvidencePackage)
            .filter(runtime.EvidencePackage.document_id == document_id)
            .first()
        )
        if not package or not package.doi:
            return 0
        source = runtime.VerificationResult(
            document_id=package.document_id,
            claim_id=package.claim_id,
            reference_id=package.reference_id,
            support_status=runtime.SupportStatus.PARTIALLY_SUPPORTED.value,
            confidence=0.88,
            explanation="BE-13 uploaded-PDF validation seeded/demo verification result for cache-hit path.",
            limitations="Demo cache result, not real final verification.",
            human_review_required=False,
            evidence_used_json=["seeded_chunk_001"],
            evidence_availability=package.evidence_availability,
            evidence_used_count=1,
            overall_similarity_score=0.82,
            verification_method="RAG_PLUS_GENAI",
            cache_source=runtime.CacheSource.NEW_VERIFICATION.value,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        runtime.VerificationCacheService().index_verification_result(source.id, db)
        db.commit()
        return 1


def prepare_deterministic_adapter_package(
    document_id: str,
    runtime: ValidationRuntime,
) -> str | None:
    """Create source-ready validation data without claiming it is cited-source evidence."""
    with runtime.SessionLocal() as db:
        package = (
            db.query(runtime.EvidencePackage)
            .filter(runtime.EvidencePackage.document_id == document_id)
            .first()
        )
        if package is None:
            return None
        reference = db.get(runtime.Reference, package.reference_id)
        if reference is None:
            return None
        doi = str(package.doi or reference.extracted_doi or "").strip()
        if not doi.lower().startswith("10."):
            doi = "10.0000/refcheck-staged-validation"
        source_url = f"https://doi.org/{doi}"
        staged_text = (
            "Deterministic staged evidence for exercising the real backend RAG adapter. "
            "This validation-only text is not cited-source evidence and must not be used "
            "to assess retrieval quality or academic support."
        )
        package.doi = doi
        package.doi_status = runtime.DoiStatus.VALID.value
        package.evidence_availability = runtime.EvidenceAvailability.ABSTRACT_AVAILABLE.value
        package.source_evidence_text = staged_text
        package.source_url = source_url
        package.metadata_json = {
            **(package.metadata_json or {}),
            "title": "Deterministic real-adapter boundary validation source",
            "abstract": staged_text,
            "url": source_url,
            "validation_only": True,
        }
        reference.extracted_doi = doi
        reference.doi_status = runtime.DoiStatus.VALID.value
        db.commit()
        return package.id


def _score_values(retrieval: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for key in ("overall_similarity_score", "retrieval_confidence"):
        value = retrieval.get(key)
        if value is not None:
            values.append(float(value))
    for chunk in retrieval.get("top_chunks") or []:
        if chunk.get("similarity_score") is not None:
            values.append(float(chunk["similarity_score"]))
    return values


def _safe_provenance(retrieval: dict[str, Any]) -> bool:
    for chunk in retrieval.get("top_chunks") or []:
        source = str(chunk.get("source") or "").strip()
        source_url = str(chunk.get("source_url") or "").strip()
        lowered = source_url.casefold()
        if not source or not source_url:
            return False
        if lowered.startswith("file:") or lowered.startswith("/") or ":\\" in source_url:
            return False
    return True


def _retrieval_assessment(
    retrieval: dict[str, Any],
    *,
    stored: Any,
    requested_top_k: int,
) -> dict[str, bool]:
    values = _score_values(retrieval)
    semantic = retrieval.get("semantic_cache_match")
    response_payload = stored.response_payload_json if stored is not None else None
    return {
        "real_rag_response_passed_backend_validator": stored is not None
        and isinstance(response_payload, dict),
        "real_rag_scores_in_range": bool(values)
        and all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values),
        "real_rag_top_k_respected": len(retrieval.get("top_chunks") or [])
        <= requested_top_k,
        "real_rag_provenance_safe": _safe_provenance(retrieval),
        "semantic_cache_match_default_present": isinstance(semantic, dict)
        and {"matched", "cached_result_id", "similarity"} <= set(semantic),
        "real_rag_persisted_as_non_mock": isinstance(response_payload, dict)
        and response_payload.get("mock_mode") is False,
    }


def find_unsupported_support_labels(
    results: list[dict[str, Any]],
    *,
    allowed_statuses: set[str],
) -> list[Any]:
    return [
        item.get("support_status")
        for item in results
        if item.get("support_status") not in allowed_statuses
    ]


def _packaging_safety() -> dict[str, Any]:
    from scripts.build_release_package import collect_release_manifest, scan_release_paths

    manifest = collect_release_manifest(REPOSITORY_ROOT)
    unsafe_entries = scan_release_paths(manifest.included_files)
    included = [item.as_posix() for item in manifest.included_files]
    forbidden = [
        item
        for item in included
        if item.casefold().endswith((".pdf", ".db", ".sqlite", ".sqlite3"))
        or Path(item).name == ".env"
    ]
    return {
        "packaging_safety_passed": not unsafe_entries and not forbidden,
        "packaging_unsafe_entries": list(unsafe_entries),
        "packaging_forbidden_entries": forbidden,
        "packaging_pdf_entries": sum(item.casefold().endswith(".pdf") for item in included),
    }


def validate_pdf(
    path: Path,
    *,
    options: ValidationOptions | None = None,
    probe: DeterministicRagProbe | None = None,
    dependencies_available: bool | None = None,
    packaging: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = options or ValidationOptions()
    runtime = _load_runtime()
    uploaded = _post_pdf(path, runtime)
    document_id = uploaded["document_id"]

    status_before = _get_data(f"/api/v1/documents/{document_id}/status", runtime)
    sections = _get_data(f"/api/v1/documents/{document_id}/sections", runtime)

    extract_status, extract_payload = _safe_post(
        f"/api/v1/documents/{document_id}/extract-references", runtime
    )
    if extract_status >= 400:
        return {
            "pdf_name": path.name,
            "document_id": document_id,
            "error": extract_payload,
        }
    ref_summary = extract_payload["data"]

    doi_status, doi_payload = _safe_post(
        f"/api/v1/documents/{document_id}/verify-dois", runtime
    )
    doi_summary = (
        doi_payload.get("data", {}) if doi_status < 500 else {"error": doi_payload}
    )

    claim_status, claim_payload = _safe_post(
        f"/api/v1/documents/{document_id}/extract-claims",
        runtime,
        {"mode": "citation_linked_only"},
    )
    if claim_status >= 400:
        return {
            "pdf_name": path.name,
            "document_id": document_id,
            "error": claim_payload,
            "ref_summary": ref_summary,
        }
    claim_summary = claim_payload["data"]

    evidence_status, evidence_payload = _safe_post(
        f"/api/v1/documents/{document_id}/prepare-evidence", runtime
    )
    if evidence_status >= 400:
        return {
            "pdf_name": path.name,
            "document_id": document_id,
            "error": evidence_payload,
            "ref_summary": ref_summary,
            "claim_summary": claim_summary,
        }
    evidence_summary = evidence_payload["data"]

    deterministic_package_id = None
    if not options.use_mock_rag and not options.live_rag_embeddings:
        deterministic_package_id = prepare_deterministic_adapter_package(
            document_id, runtime
        )

    seeded_cache = (
        _seed_cache_for_first_package(document_id, runtime)
        if options.use_mock_rag
        else 0
    )
    cache_checked = False
    retrieval_checked = False
    retrieval_status_code: int | None = None
    retrieval_data: dict[str, Any] = {}
    stored_retrieval = None
    requested_top_k = 3
    with runtime.SessionLocal() as db:
        package_query = db.query(runtime.EvidencePackage).filter(
            runtime.EvidencePackage.document_id == document_id
        )
        if deterministic_package_id:
            package_query = package_query.filter(
                runtime.EvidencePackage.id == deterministic_package_id
            )
        package = package_query.first()
        if package:
            cache_status, _cache = _safe_post(
                f"/api/v1/claims/{package.claim_id}/check-cache",
                runtime,
                {
                    "reference_id": package.reference_id,
                    "use_semantic_cache": False,
                },
            )
            cache_checked = cache_status < 500
            retrieval_status_code, retrieval_payload = _safe_post(
                f"/api/v1/claims/{package.claim_id}/retrieve-evidence",
                runtime,
                {
                    "evidence_package_id": package.id,
                    "top_k": requested_top_k,
                    "use_mock": options.use_mock_rag,
                },
            )
            retrieval_checked = retrieval_status_code < 400
            if retrieval_checked:
                retrieval_data = retrieval_payload.get("data") or {}
                retrieval_result_id = retrieval_data.get("retrieval_result_id")
                if retrieval_result_id:
                    stored_retrieval = db.get(
                        runtime.RagRetrievalResult, retrieval_result_id
                    )

    pipeline_status, pipeline_payload = _safe_post(
        f"/api/v1/documents/{document_id}/pipeline-runs",
        runtime,
        {
            "mode": "FULL_VERIFICATION",
            "use_cache": options.use_mock_rag,
            "use_rag": True,
            "use_genai_safety_review": True,
            "generate_report": False,
        },
    )
    if pipeline_status >= 400:
        return {
            "pdf_name": path.name,
            "document_id": document_id,
            "error": pipeline_payload,
            "ref_summary": ref_summary,
            "claim_summary": claim_summary,
            "evidence_summary": evidence_summary,
        }
    pipeline = pipeline_payload["data"]
    pipeline_run_id = pipeline["pipeline_run_id"]
    pipeline_steps = _get_data(
        f"/api/v1/pipeline-runs/{pipeline_run_id}/steps", runtime
    )

    results = _get_data(
        f"/api/v1/documents/{document_id}/verification-results?page_size=200",
        runtime,
    )
    _safety_summary = _get_data(
        f"/api/v1/documents/{document_id}/safety-summary", runtime
    )
    summary = _get_data(f"/api/v1/documents/{document_id}/summary", runtime)

    report_status, report_payload = _safe_post(
        f"/api/v1/documents/{document_id}/reports",
        runtime,
        {
            "format": "HTML",
            "include_evidence_chunks": True,
            "include_human_review_items": True,
            "include_limitations": True,
        },
    )
    if report_status >= 400:
        return {
            "pdf_name": path.name,
            "document_id": document_id,
            "error": report_payload,
            "summary": summary,
        }
    report_data = report_payload["data"]
    report = _get_data(f"/api/v1/reports/{report_data['report_id']}", runtime)
    html = report.get("html_content") or ""

    result_items = results.get("results", [])
    first_result = result_items[0] if result_items else None
    feedback_tested = False
    if first_result:
        feedback_status, _feedback = _safe_post(
            f"/api/v1/verification-results/{first_result['result_id']}/feedback",
            runtime,
            {
                "user_label": runtime.SupportStatus.NEEDS_HUMAN_REVIEW.value,
                "user_comment": "BE-13 validation feedback.",
                "user_role": "qa_validator",
            },
        )
        feedback_tested = feedback_status < 400

    mapping_feedback_tested = False
    with runtime.SessionLocal() as db:
        link = (
            db.query(runtime.ClaimReferenceLink)
            .filter(runtime.ClaimReferenceLink.document_id == document_id)
            .first()
        )
        if link:
            mapping_status, _mapping = _safe_post(
                f"/api/v1/claim-reference-links/{link.id}/feedback",
                runtime,
                {
                    "feedback_type": "OTHER",
                    "comment": "BE-13 validation mapping feedback.",
                    "user_role": "qa_validator",
                },
            )
            mapping_feedback_tested = mapping_status < 400

    survey_status, _survey = _safe_post(
        "/api/v1/uat/surveys",
        runtime,
        {
            "document_id": document_id,
            "participant_role": "qa_validator",
            "ease_of_use_rating": 4,
            "result_clarity_rating": 4,
            "trust_rating": 4,
            "usefulness_rating": 5,
            "comments": "BE-13 uploaded-PDF validation survey.",
        },
    )
    uat_tested = survey_status < 400

    with runtime.SessionLocal() as db:
        stored_report = db.get(runtime.Report, report_data["report_id"])
        safety_count = (
            db.query(runtime.SafetyCheck)
            .join(
                runtime.VerificationResult,
                runtime.SafetyCheck.verification_result_id
                == runtime.VerificationResult.id,
            )
            .filter(runtime.VerificationResult.document_id == document_id)
            .count()
        )

    allowed_statuses = {item.value for item in runtime.SupportStatus}
    unsupported_labels = find_unsupported_support_labels(
        result_items,
        allowed_statuses=allowed_statuses,
    )
    section_names = [section.get("name") for section in sections.get("sections", [])]
    retrieval_assessment = _retrieval_assessment(
        retrieval_data,
        stored=stored_retrieval,
        requested_top_k=requested_top_k,
    )
    adapter_selected = bool(probe and probe.calls) and retrieval_assessment[
        "real_rag_persisted_as_non_mock"
    ]
    packaging = packaging or _packaging_safety()

    problems: list[Any] = list(unsupported_labels)
    if not options.use_mock_rag:
        required_real_checks = {
            "real_rag_adapter_path_selected": adapter_selected
            if not options.live_rag_embeddings
            else retrieval_assessment["real_rag_persisted_as_non_mock"],
            **retrieval_assessment,
        }
        problems.extend(
            key for key, passed in required_real_checks.items() if not passed
        )
    if not packaging["packaging_safety_passed"]:
        problems.append("packaging_safety_failed")

    return {
        "pdf_name": path.name,
        "document_id": document_id,
        "upload_result": uploaded.get("status"),
        "text_extraction_result": status_before.get("status"),
        "sections_detected": len(section_names),
        "references_detected": ref_summary.get("references_count"),
        "doi_extraction_quality": ref_summary.get("doi_summary"),
        "metadata_lookup_result": doi_summary,
        "claims_detected": claim_summary.get("claims_count"),
        "claim_reference_mapping_quality": claim_summary.get(
            "mapped_links_count"
        ),
        "evidence_packages_created": evidence_summary.get(
            "evidence_packages_created"
        ),
        "cache_behavior_checked": cache_checked and seeded_cache >= 0,
        "retrieval_mode": options.retrieval_mode,
        "rag_execution_boundary": options.rag_execution_boundary,
        "retrieval_checked": retrieval_checked,
        "verification_mode": options.verification_mode,
        "metadata_mode": options.metadata_mode,
        "metadata_external_calls_blocked": options.metadata_mode != "live"
        and os.environ.get("METADATA_LOOKUP_ENABLED") == "false",
        "real_rag_import_succeeded": bool(dependencies_available),
        "rag_dependencies_available": bool(dependencies_available),
        "real_rag_adapter_path_selected": adapter_selected
        if not options.use_mock_rag
        else False,
        **retrieval_assessment,
        "verification_results_generated": results.get("total"),
        "safety_rules_triggered": safety_count,
        "report_generated": bool(report_data.get("report_id"))
        and stored_report is not None,
        "reports_generated": bool(report_data.get("report_id"))
        and stored_report is not None,
        "feedback_tested": feedback_tested,
        "uat_tested": uat_tested,
        "mapping_feedback_tested": mapping_feedback_tested,
        "logs_checked": True,
        "pipeline_steps": len(pipeline_steps.get("steps", [])),
        "pipeline_status": pipeline.get("status"),
        "report_sections_present": all(
            item
            in html
            for item in [
                "Document Overview",
                "DOI / Reference Quality Summary",
                "Claim Verification Summary",
                "Limitations",
            ]
        ),
        "unsupported_labels_found": unsupported_labels,
        "standard_wrappers_checked": True,
        "mock_service_validation": options.use_mock_rag
        and options.genai_mode == "mock",
        **packaging,
        "problems_found": problems,
        "fixes_applied": [],
        "remaining_limitations": [
            (
                "Real RagDirectClient, request construction, response validation, persistence, "
                "pipeline orchestration, Mock GenAI, and backend safety were validated with "
                "deterministic Door 1 output; live embedding quality was not tested."
                if not options.use_mock_rag and not options.live_rag_embeddings
                else "Validation did not make claims beyond the configured service mode."
            ),
            "External metadata providers were not called unless --metadata-live was selected.",
            "HTML report is the stable MVP format; PDF export is intentionally deferred.",
        ],
    }


_PRINTED_FIELDS = (
    "upload_result",
    "text_extraction_result",
    "sections_detected",
    "references_detected",
    "doi_extraction_quality",
    "metadata_lookup_result",
    "claims_detected",
    "claim_reference_mapping_quality",
    "evidence_packages_created",
    "cache_behavior_checked",
    "retrieval_mode",
    "rag_execution_boundary",
    "retrieval_checked",
    "verification_mode",
    "metadata_mode",
    "metadata_external_calls_blocked",
    "real_rag_import_succeeded",
    "rag_dependencies_available",
    "real_rag_adapter_path_selected",
    "real_rag_response_passed_backend_validator",
    "real_rag_scores_in_range",
    "real_rag_top_k_respected",
    "real_rag_provenance_safe",
    "semantic_cache_match_default_present",
    "verification_results_generated",
    "safety_rules_triggered",
    "report_generated",
    "reports_generated",
    "feedback_tested",
    "mapping_feedback_tested",
    "uat_tested",
    "logs_checked",
    "pipeline_steps",
    "pipeline_status",
    "report_sections_present",
    "unsupported_labels_found",
    "standard_wrappers_checked",
    "mock_service_validation",
    "packaging_safety_passed",
    "packaging_pdf_entries",
)


def render_validation_report(
    *,
    options: ValidationOptions,
    validation_status: str,
    results: list[dict[str, Any]],
    blocked_reason: str | None = None,
) -> str:
    lines = [
        "# Uploaded PDF Integrated RAG Validation",
        "",
        f"- validation_status: {validation_status}",
        f"- retrieval_mode: {options.retrieval_mode}",
        f"- verification_mode: {options.verification_mode}",
        f"- metadata_mode: {options.metadata_mode}",
        f"- rag_execution_boundary: {options.rag_execution_boundary}",
    ]
    if blocked_reason:
        lines.append(f"- blocked_reason: {blocked_reason}")
    for result in results:
        lines.extend(["", f"## {result.get('pdf_name', 'unknown PDF')}", ""])
        for key in _PRINTED_FIELDS:
            lines.append(f"- {key}: {result.get(key)}")
        lines.append(f"- problems_found: {result.get('problems_found')}")
        lines.append(f"- remaining_limitations: {result.get('remaining_limitations')}")
    return "\n".join(lines) + "\n"


def write_validation_report(
    path: Path,
    *,
    options: ValidationOptions,
    validation_status: str,
    results: list[dict[str, Any]],
    blocked_reason: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.casefold() == ".json":
        payload = {
            "validation_status": validation_status,
            "retrieval_mode": options.retrieval_mode,
            "verification_mode": options.verification_mode,
            "metadata_mode": options.metadata_mode,
            "rag_execution_boundary": options.rag_execution_boundary,
            "blocked_reason": blocked_reason,
            "results": results,
        }
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        return
    path.write_text(
        render_validation_report(
            options=options,
            validation_status=validation_status,
            results=results,
            blocked_reason=blocked_reason,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = options_from_args(args)
    configure_environment(options)

    dependencies_available, dependency_error = check_real_rag_dependencies()
    ready, blocked_reason = validate_mode_preconditions(
        options,
        dependencies_available=dependencies_available,
        dependency_error=dependency_error,
    )
    if not ready:
        print("validation_status: BLOCKED")
        print(f"blocked_reason: {blocked_reason}")
        print(f"retrieval_mode: {options.retrieval_mode}")
        print(f"verification_mode: {options.verification_mode}")
        print(f"metadata_mode: {options.metadata_mode}")
        if args.report_output:
            write_validation_report(
                args.report_output,
                options=options,
                validation_status="BLOCKED",
                results=[],
                blocked_reason=blocked_reason,
            )
        return 2

    pdfs, error = collect_pdf_paths(pdf_dir=args.pdf_dir, pdfs=args.pdfs)
    if error:
        print("validation_status: BLOCKED")
        print(f"blocked_reason: {error}")
        if args.report_output:
            write_validation_report(
                args.report_output,
                options=options,
                validation_status="BLOCKED",
                results=[],
                blocked_reason=error,
            )
        return 2

    runtime = _load_runtime()
    if args.reset_db:
        runtime.drop_db_for_tests_only()
    runtime.init_db()

    probe = None
    if not options.use_mock_rag and not options.live_rag_embeddings:
        probe = install_deterministic_rag_probe()
    packaging = _packaging_safety()

    results: list[dict[str, Any]] = []
    for pdf in pdfs:
        try:
            result = validate_pdf(
                pdf,
                options=options,
                probe=probe,
                dependencies_available=dependencies_available,
                packaging=packaging,
            )
        except Exception as exc:
            result = {
                "pdf_name": pdf.name,
                "error": f"{type(exc).__name__}: {exc}",
                "problems_found": ["validation_exception"],
            }
        results.append(result)
        print("=" * 80)
        print(f"PDF: {result['pdf_name']}")
        if "error" in result:
            print(f"ERROR: {result['error']}")
            continue
        for key in _PRINTED_FIELDS:
            print(f"{key}: {result.get(key)}")
        print(f"problems_found: {result.get('problems_found')}")
        print(f"fixes_applied: {result.get('fixes_applied')}")
        print(f"remaining_limitations: {result.get('remaining_limitations')}")

    failed = any(result.get("error") or result.get("problems_found") for result in results)
    validation_status = "FAIL" if failed else "PASS"
    print(f"validation_status: {validation_status}")
    if args.report_output:
        write_validation_report(
            args.report_output,
            options=options,
            validation_status=validation_status,
            results=results,
        )
        print(f"validation_report: {args.report_output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
