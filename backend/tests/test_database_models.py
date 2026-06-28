from __future__ import annotations

from app.db.init_db import init_db, list_table_names
from app.db.session import session_scope
from app.models import (
    ClaimCacheIndex,
    ClaimReferenceLink,
    Citation,
    Document,
    DocumentSection,
    EvidencePackage,
    PipelineStep,
    PromptRun,
    RagRetrievalResult,
    SafetyCheck,
    SourceMetadata,
    UatSurvey,
    UserFeedback,
    VerificationResult,
)
from app.models.enums import (
    CacheSource,
    ClaimType,
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
    PipelineStatus,
    PipelineStepStatus,
    SafetyRiskLevel,
    SupportStatus,
    UploadType,
)
from app.repositories import ClaimRepository, DocumentRepository, PipelineRepository, ReferenceRepository, VerificationResultRepository


def test_database_initialization_creates_all_be2_tables() -> None:
    init_db()
    tables = set(list_table_names())
    assert {
        "documents",
        "document_sections",
        "references",
        "source_metadata",
        "claims",
        "citations",
        "claim_reference_links",
        "evidence_packages",
        "rag_retrieval_results",
        "verification_results",
        "safety_checks",
        "reports",
        "user_feedback",
        "uat_surveys",
        "pipeline_runs",
        "pipeline_steps",
        "prompt_runs",
        "claim_cache_index",
    }.issubset(tables)


def test_required_enum_values_match_final_contract() -> None:
    assert DocumentStatus.UPLOADED.value == "UPLOADED"
    assert DocumentStatus.REPORT_GENERATED.value == "REPORT_GENERATED"
    assert PipelineStatus.PARTIAL_FAILED.value == "PARTIAL_FAILED"
    assert PipelineStepStatus.SKIPPED.value == "SKIPPED"
    assert DoiStatus.MALFORMED.value == "MALFORMED"
    assert MetadataStatus.METADATA_UNAVAILABLE.value == "METADATA_UNAVAILABLE"
    assert ClaimType.EMPIRICAL.value == "EMPIRICAL"
    assert MappingStatus.NEEDS_HUMAN_REVIEW.value == "NEEDS_HUMAN_REVIEW"
    assert EvidenceAvailability.FULL_TEXT_AVAILABLE.value == "FULL_TEXT_AVAILABLE"
    assert SupportStatus.INSUFFICIENT_EVIDENCE.value == "INSUFFICIENT_EVIDENCE"
    assert CacheSource.SEMANTIC_CACHE.value == "SEMANTIC_CACHE"
    assert SafetyRiskLevel.UNKNOWN.value == "UNKNOWN"
    assert UploadType.PDF.value == "PDF"


def test_create_document_reference_claim_link_pipeline_and_result() -> None:
    with session_scope() as db:
        document = DocumentRepository(db).create(
            filename="paper.txt",
            title="Database Design Demo",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.UPLOADED.value,
            raw_text="A demo claim with citation.",
            cleaned_text="A demo claim with citation.",
            commit=False,
        )
        db.flush()
        assert document.id.startswith("doc_")

        section = DocumentSection(document_id=document.id, name="Introduction", order_index=1, text="Demo section")
        db.add(section)
        reference = ReferenceRepository(db).create(
            document_id=document.id,
            raw_reference="Smith, J. (2024). Demo paper.",
            reference_key="Smith2024",
            extracted_title="Demo paper",
            extracted_doi="10.1234/demo",
            commit=False,
        )
        claim = ClaimRepository(db).create(
            document_id=document.id,
            claim_text="Demo claim is stored in the database.",
            claim_type=ClaimType.EMPIRICAL.value,
            commit=False,
        )
        db.flush()

        metadata = SourceMetadata(
            reference_id=reference.id,
            doi="10.1234/demo",
            title="Demo paper",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            raw_metadata_json={"source": "seed"},
        )
        citation = Citation(
            document_id=document.id,
            claim_id=claim.id,
            raw_citation="(Smith, 2024)",
            mapped_reference_id=reference.id,
            mapping_confidence=0.9,
        )
        db.add_all([metadata, citation])
        db.flush()

        link = ClaimReferenceLink(
            document_id=document.id,
            claim_id=claim.id,
            citation_id=citation.id,
            reference_id=reference.id,
            mapping_status=MappingStatus.MAPPED.value,
            mapping_confidence=0.9,
        )
        db.add(link)
        evidence = EvidencePackage(
            document_id=document.id,
            claim_id=claim.id,
            reference_id=reference.id,
            citation_text="(Smith, 2024)",
            doi="10.1234/demo",
            doi_status=DoiStatus.FOUND.value,
            metadata_json={"title": "Demo paper"},
            evidence_availability=EvidenceAvailability.METADATA_ONLY.value,
            embedding_model_version="demo-embedding-v1",
            prompt_version="demo-prompt-v1",
            verification_policy_version="demo-policy-v1",
        )
        db.add(evidence)
        db.flush()

        retrieval = RagRetrievalResult(
            document_id=document.id,
            claim_id=claim.id,
            reference_id=reference.id,
            evidence_package_id=evidence.id,
            retrieval_status="STUBBED",
            top_chunks_json=[{"chunk": "metadata only"}],
            overall_similarity_score=0.75,
        )
        db.add(retrieval)
        result = VerificationResultRepository(db).create(
            document_id=document.id,
            claim_id=claim.id,
            reference_id=reference.id,
            support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
            confidence=0.55,
            explanation="BE-2 persistence test only.",
            commit=False,
        )
        db.flush()
        safety = SafetyCheck(
            verification_result_id=result.id,
            safety_status="TRIGGERED",
            risk_level=SafetyRiskLevel.MEDIUM.value,
            backend_rule_triggered="LOW_CONFIDENCE_BE2_TEST",
        )
        feedback = UserFeedback(
            document_id=document.id,
            result_id=result.id,
            link_id=link.id,
            feedback_type="RESULT_LABEL",
            user_label="NEEDS_HUMAN_REVIEW",
        )
        survey = UatSurvey(document_id=document.id, participant_role="student", ease_of_use_rating=4)
        prompt_run = PromptRun(
            document_id=document.id,
            claim_id=claim.id,
            prompt_type="VERIFICATION_STUB",
            model_provider="groq",
            model_name="meta-llama/llama-4-scout-17b-16e-instruct",
            prompt_version="be2-test",
            success=True,
            output_json={"stub": True},
        )
        cache_entry = ClaimCacheIndex(
            normalized_claim_hash="hash-demo",
            normalized_claim_text="demo claim is stored in the database",
            doi="10.1234/demo",
            reference_id=reference.id,
            verification_result_id=result.id,
            support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
            confidence=0.55,
            evidence_version="evidence-v1",
            embedding_model_version="embedding-v1",
            prompt_version="prompt-v1",
            verification_policy_version="policy-v1",
            cache_source=CacheSource.NEW_VERIFICATION.value,
        )
        db.add_all([safety, feedback, survey, prompt_run, cache_entry])

        pipeline = PipelineRepository(db).create_run(
            document_id=document.id, status=PipelineStatus.QUEUED.value, commit=False
        )
        db.flush()
        step = PipelineRepository(db).create_step(
            pipeline_run_id=pipeline.id,
            step_name="BE-2_DATABASE_DESIGN_CHECK",
            status=PipelineStepStatus.SUCCEEDED.value,
            commit=False,
        )
        document.latest_pipeline_run_id = pipeline.id

        db.flush()
        assert reference.document_id == document.id
        assert claim.document_id == document.id
        assert link.claim_id == claim.id
        assert link.reference_id == reference.id
        assert retrieval.evidence_package_id == evidence.id
        assert result.document_id == document.id
        assert safety.verification_result_id == result.id
        assert pipeline.document_id == document.id
        assert step.pipeline_run_id == pipeline.id
        assert prompt_run.model_name == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert cache_entry.normalized_claim_hash == "hash-demo"


def test_repository_get_operations() -> None:
    with session_scope() as db:
        document = DocumentRepository(db).create(
            filename="repo.txt",
            title="Repository Test",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.UPLOADED.value,
            commit=True,
        )
        loaded = DocumentRepository(db).get(document.id)
        assert loaded is not None
        assert loaded.id == document.id
        assert loaded.title == "Repository Test"
