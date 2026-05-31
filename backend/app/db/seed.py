from datetime import datetime, timezone

from .database import SessionLocal
from .models import (
    CacheIndex,
    CacheSource,
    CacheStatus,
    Claim,
    ClaimReferenceLink,
    Citation,
    Document,
    DocumentProcessingStatus,
    DocumentSection,
    DoiStatus,
    EvidenceLevel,
    EvidencePackage,
    FeedbackType,
    MetadataStatus,
    Reference,
    RetrievalChunk,
    RetrievalResult,
    RetrievalStatus,
    SafetyCheck,
    SectionType,
    SourceMetadata,
    SupportStatus,
    UploadType,
    UserFeedback,
    VerificationMethod,
    VerificationResult,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def seed_demo_data() -> None:
    with SessionLocal() as session:
        existing = session.query(Document).count()
        if existing:
            return

        # ── Document 1 ───────────────────────────────────────────────────────
        document = Document(
            document_id="doc_123",
            title="Sample Scientific Reference Verification Paper",
            filename="sample_paper.pdf",
            upload_type=UploadType.PDF,
            status=DocumentProcessingStatus.VERIFIED,
            file_size_bytes=204800,
            page_count=12,
            references_count=2,
            claims_count=2,
            created_at=now(),
            updated_at=now(),
        )

        section_title = DocumentSection(
            document_id=document.document_id,
            section_id="sec_001",
            name="Title",
            type=SectionType.title,
            order_index=0,
            text_preview="Sample Paper Title",
            full_text="Sample Paper Title",
            start_char=0,
            end_char=20,
        )
        section_abstract = DocumentSection(
            document_id=document.document_id,
            section_id="sec_002",
            name="Abstract",
            type=SectionType.abstract,
            order_index=1,
            text_preview="Abstract text goes here...",
            full_text="Abstract text goes here. This paper demonstrates methods for scientific reference verification.",
            start_char=21,
            end_char=200,
        )

        # ── References ───────────────────────────────────────────────────────
        reference_one = Reference(
            reference_id="ref_456",
            document_id=document.document_id,
            raw_reference="Smith J. et al. (2020). Title of Paper. Journal Name. DOI: 10.1000/xyz123",
            extracted_title="Title of Paper",
            extracted_authors=["Smith, J.", "Doe, A."],
            extracted_year=2020,
            extracted_doi="10.1000/xyz123",
            doi_normalized="10.1000/xyz123",
            doi_status=DoiStatus.FOUND,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED,
            metadata_match_score=0.96,
            position=1,
            created_at=now(),
            updated_at=now(),
        )

        metadata_one = SourceMetadata(
            reference_id=reference_one.reference_id,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED,
            doi="10.1000/xyz123",
            title="Title of the Referenced Paper",
            authors=["Smith, J.", "Doe, A."],
            year=2020,
            journal="Journal of Science",
            publisher="Example Publisher",
            url="https://doi.org/10.1000/xyz123",
            abstract="Abstract of the referenced paper...",
            fetched_at=now(),
            created_at=now(),
            updated_at=now(),
        )

        reference_two = Reference(
            reference_id="ref_457",
            document_id=document.document_id,
            raw_reference="Jones E. (2021). Another Paper. Journal Two. DOI: malformed-doi",
            extracted_title="Another Paper",
            extracted_authors=["Jones, E."],
            extracted_year=2021,
            extracted_doi=None,
            doi_normalized=None,
            doi_status=DoiStatus.MALFORMED,
            metadata_status=MetadataStatus.NOT_LOOKED_UP,
            position=2,
            created_at=now(),
            updated_at=now(),
        )

        # ── Claims ───────────────────────────────────────────────────────────
        claim_one = Claim(
            claim_id="clm_789",
            document_id=document.document_id,
            claim_text="This study demonstrates that X causes Y.",
            claim_type="causal",
            section_name="Results",
            source_paragraph="In the results, we show that X causes Y under all tested conditions.",
            citation_text="[1]",
            page_number=5,
            paragraph_index=2,
            sentence_index=1,
            extraction_confidence=0.92,
            mapping_status="MAPPED",
            created_at=now(),
            updated_at=now(),
        )

        claim_two = Claim(
            claim_id="clm_790",
            document_id=document.document_id,
            claim_text="Results show a significant correlation between A and B.",
            claim_type="correlational",
            section_name="Discussion",
            source_paragraph="Results show a significant correlation between A and B (p < 0.01).",
            citation_text="[2]",
            page_number=7,
            paragraph_index=3,
            sentence_index=2,
            extraction_confidence=0.85,
            mapping_status="MAPPED",
            created_at=now(),
            updated_at=now(),
        )

        # ── Citations ────────────────────────────────────────────────────────
        citation_one = Citation(
            citation_id="cit_001",
            claim_id=claim_one.claim_id,
            citation_text="[1]",
            citation_style="numeric",
            raw_marker="[1]",
            mapped_reference_id=reference_one.reference_id,
            mapping_confidence=0.98,
            mapping_uncertain=False,
            created_at=now(),
            updated_at=now(),
        )

        citation_two = Citation(
            citation_id="cit_002",
            claim_id=claim_two.claim_id,
            citation_text="[2]",
            citation_style="numeric",
            raw_marker="[2]",
            mapped_reference_id=reference_two.reference_id,
            mapping_confidence=0.85,
            mapping_uncertain=False,
            created_at=now(),
            updated_at=now(),
        )

        # ── Claim-Reference Links ────────────────────────────────────────────
        link_one = ClaimReferenceLink(
            link_id="lnk_001",
            claim_id=claim_one.claim_id,
            citation_id=citation_one.citation_id,
            reference_id=reference_one.reference_id,
            mapping_status="MAPPED",
            mapping_confidence=0.98,
            created_at=now(),
            updated_at=now(),
        )

        link_two = ClaimReferenceLink(
            link_id="lnk_002",
            claim_id=claim_two.claim_id,
            citation_id=citation_two.citation_id,
            reference_id=reference_two.reference_id,
            mapping_status="MAPPED",
            mapping_confidence=0.85,
            created_at=now(),
            updated_at=now(),
        )

        # ── Evidence Packages ────────────────────────────────────────────────
        evidence_one = EvidencePackage(
            package_id="pkg_001",
            claim_id=claim_one.claim_id,
            reference_id=reference_one.reference_id,
            evidence_level=EvidenceLevel.ABSTRACT_AVAILABLE,
            source_evidence_text="The abstract discusses key experimental findings supporting the claim.",
            source_evidence_url="https://doi.org/10.1000/xyz123",
            embedding_model_version="text-embedding-3-large",
            prompt_version="v1.0",
            verification_policy_version="policy-2026-05",
            created_at=now(),
            updated_at=now(),
        )

        evidence_two = EvidencePackage(
            package_id="pkg_002",
            claim_id=claim_two.claim_id,
            reference_id=reference_two.reference_id,
            evidence_level=EvidenceLevel.METADATA_ONLY,
            source_evidence_text=None,
            source_evidence_url=None,
            embedding_model_version="text-embedding-3-large",
            prompt_version="v1.0",
            verification_policy_version="policy-2026-05",
            created_at=now(),
            updated_at=now(),
        )

        # ── Retrieval Results ────────────────────────────────────────────────
        retrieval_one = RetrievalResult(
            retrieval_result_id="ret_001",
            claim_id=claim_one.claim_id,
            retrieval_status=RetrievalStatus.COMPLETED,
            overall_similarity_score=0.92,
            retrieval_confidence=0.89,
            top_k=3,
            created_at=now(),
            updated_at=now(),
        )

        chunk_one = RetrievalChunk(
            chunk_id="chunk_001",
            retrieval_result_id=retrieval_one.retrieval_result_id,
            chunk_text="Experimental evidence shows that X causes Y in a dose-dependent fashion.",
            similarity_score=0.93,
            evidence_type="abstract",
            source="https://doi.org/10.1000/xyz123",
            created_at=now(),
        )

        chunk_two = RetrievalChunk(
            chunk_id="chunk_002",
            retrieval_result_id=retrieval_one.retrieval_result_id,
            chunk_text="Supporting context from the introduction discusses the causal mechanism.",
            similarity_score=0.87,
            evidence_type="full_text",
            source="https://doi.org/10.1000/xyz123",
            created_at=now(),
        )

        retrieval_two = RetrievalResult(
            retrieval_result_id="ret_002",
            claim_id=claim_two.claim_id,
            retrieval_status=RetrievalStatus.COMPLETED,
            overall_similarity_score=0.61,
            retrieval_confidence=0.55,
            top_k=3,
            created_at=now(),
            updated_at=now(),
        )

        chunk_three = RetrievalChunk(
            chunk_id="chunk_003",
            retrieval_result_id=retrieval_two.retrieval_result_id,
            chunk_text="Metadata only — full text unavailable for this reference.",
            similarity_score=0.61,
            evidence_type="metadata",
            source=None,
            created_at=now(),
        )

        # ── Verification Results ─────────────────────────────────────────────
        verification_one = VerificationResult(
            result_id="vr_001",
            claim_id=claim_one.claim_id,
            citation_id=citation_one.citation_id,
            reference_id=reference_one.reference_id,
            claim_reference_link_id=link_one.link_id,
            support_status=SupportStatus.SUPPORTED,
            confidence=0.91,
            human_review_required=False,
            cache_source=CacheSource.NEW_VERIFICATION,
            evidence_availability=EvidenceLevel.ABSTRACT_AVAILABLE,
            evidence_used_count=2,
            overall_similarity_score=0.92,
            verification_method=VerificationMethod.RAG_GENAI,
            explanation="The abstract of the cited paper directly supports the claim.",
            safety_risk_level="LOW",
            created_at=now(),
            updated_at=now(),
        )

        verification_two = VerificationResult(
            result_id="vr_002",
            claim_id=claim_two.claim_id,
            citation_id=citation_two.citation_id,
            reference_id=reference_two.reference_id,
            claim_reference_link_id=link_two.link_id,
            support_status=SupportStatus.NEEDS_HUMAN_REVIEW,
            confidence=None,
            human_review_required=True,
            cache_source=CacheSource.NEW_VERIFICATION,
            evidence_availability=EvidenceLevel.METADATA_ONLY,
            evidence_used_count=0,
            overall_similarity_score=0.61,
            verification_method=VerificationMethod.RAG_GENAI,
            explanation="Safety rules triggered — result escalated to human review.",
            safety_risk_level="HIGH",
            created_at=now(),
            updated_at=now(),
        )

        # ── Safety Checks ────────────────────────────────────────────────────
        safety_one = SafetyCheck(
            check_id="safe_001",
            verification_result_id=verification_one.result_id,
            rule_id="missing_doi",
            triggered=False,
            details={"message": "DOI present and valid."},
            created_at=now(),
        )

        safety_two = SafetyCheck(
            check_id="safe_002",
            verification_result_id=verification_two.result_id,
            rule_id="missing_doi",
            triggered=True,
            details={"message": "Reference has no valid DOI and cannot be verified against a metadata source."},
            overridden_to="NEEDS_HUMAN_REVIEW",
            created_at=now(),
        )

        safety_three = SafetyCheck(
            check_id="safe_003",
            verification_result_id=verification_two.result_id,
            rule_id="low_genai_confidence",
            triggered=True,
            details={"confidence": 0.41, "threshold": 0.60, "message": "GenAI confidence below threshold."},
            overridden_to="NEEDS_HUMAN_REVIEW",
            created_at=now(),
        )

        # ── User Feedback ────────────────────────────────────────────────────
        feedback_one = UserFeedback(
            feedback_id="fb_001",
            verification_result_id=verification_one.result_id,
            claim_reference_link_id=link_one.link_id,
            feedback_type=FeedbackType.VERIFICATION_RESULT,
            user_label="SUPPORTED",
            user_comment="The claim is well-supported by the cited evidence.",
            user_role="researcher",
            suggested_reference_id=None,
            created_at=now(),
        )

        # ── Cache Index ──────────────────────────────────────────────────────
        cache_entry = CacheIndex(
            cache_id="cache_001",
            claim_id=claim_one.claim_id,
            cache_status=CacheStatus.EXACT_CACHE,
            cache_source=CacheSource.EXACT_CACHE,
            matched_result_id=verification_one.result_id,
            semantic_similarity=0.94,
            reuse_allowed=True,
            created_at=now(),
        )

        # ── Persist all ─────────────────────────────────────────────────────
        session.add(document)
        session.flush()

        session.add_all([section_title, section_abstract])
        session.add_all([reference_one, reference_two])
        session.flush()

        session.add(metadata_one)
        session.flush()

        session.add_all([claim_one, claim_two])
        session.flush()

        session.add_all([citation_one, citation_two])
        session.flush()

        session.add_all([link_one, link_two])
        session.flush()

        session.add_all([evidence_one, evidence_two])
        session.add_all([retrieval_one, retrieval_two])
        session.flush()

        session.add_all([chunk_one, chunk_two, chunk_three])
        session.flush()

        session.add_all([verification_one, verification_two])
        session.flush()

        session.add_all([safety_one, safety_two, safety_three])
        session.add(feedback_one)
        session.add(cache_entry)
        session.commit()

        # ── Document 2 (in-progress) ─────────────────────────────────────────
        second_document = Document(
            document_id="doc_124",
            title="Plain Text Demo Document",
            filename="text_input.txt",
            upload_type=UploadType.TEXT,
            status=DocumentProcessingStatus.TEXT_EXTRACTING,
            file_size_bytes=8192,
            page_count=None,
            references_count=0,
            claims_count=0,
            created_at=now(),
            updated_at=now(),
        )
        session.add(second_document)
        session.commit()

        seed_pipeline_run_and_report(session)


def seed_pipeline_run_and_report(session) -> None:
    """Seed a completed pipeline run and generated report for doc_123."""
    from .models import (
        PipelineRun, PipelineRunStep, PipelineRunStatus, PipelineRunMode,
        PipelineStepStatus, Report, ReportFormat, UatSurvey,
    )

    # Pipeline run
    run = PipelineRun(
        pipeline_run_id="run_abc123",
        document_id="doc_123",
        status=PipelineRunStatus.COMPLETED,
        mode=PipelineRunMode.full,
        progress_percentage=100,
        current_step=None,
        error_detail=None,
        use_cache=True,
        use_rag=True,
        use_genai_safety_review=True,
        generate_report=True,
        created_at=now(),
        updated_at=now(),
        completed_at=now(),
    )
    session.add(run)
    session.flush()

    # Pipeline steps
    all_steps = [
        "TEXT_EXTRACTION", "SECTION_DETECTION", "REFERENCE_EXTRACTION",
        "DOI_LOOKUP", "CLAIM_EXTRACTION", "CITATION_MAPPING",
        "EVIDENCE_PREPARATION", "CACHE_CHECK", "RAG_RETRIEVAL",
        "GENAI_VERIFICATION", "SAFETY_CHECK", "REPORT_GENERATION",
    ]
    for step_name in all_steps:
        session.add(PipelineRunStep(
            pipeline_run_id=run.pipeline_run_id,
            step=step_name,
            status=PipelineStepStatus.COMPLETED,
            started_at=now(),
            completed_at=now(),
            error_detail=None,
        ))
    session.flush()

    # Report
    report = Report(
        report_id="rpt_doc123_001",
        document_id="doc_123",
        title="Verification Report — Sample Scientific Reference Verification Paper",
        format=ReportFormat.JSON,
        total_claims=2,
        total_references=2,
        supported=1,
        partially_supported=0,
        not_supported=0,
        insufficient_evidence=0,
        needs_human_review=1,
        valid_dois=1,
        missing_dois=0,
        invalid_dois=1,
        overall_risk_level="MEDIUM",
        high_risk_claim_ids=["clm_790"],
        safety_rules_triggered=["missing_doi", "low_genai_confidence"],
        human_review_recommendations=["clm_790"],
        limitations="One reference has a malformed DOI and could not be fully verified.",
        html_content=None,
        generated_at=now(),
        created_at=now(),
        updated_at=now(),
    )
    session.add(report)
    session.flush()

    # UAT Survey
    survey = UatSurvey(
        survey_id="srv_demo_001",
        document_id="doc_123",
        user_id="user_researcher_01",
        responses=[
            {"question_id": "q1", "answer": "The verification results were accurate."},
            {"question_id": "q2", "answer": "The human review flag was appropriate."},
        ],
        overall_rating=4,
        free_text="Overall a good experience. The pipeline was fast and results were clear.",
        created_at=now(),
    )
    session.add(survey)
    session.commit()
