from __future__ import annotations

from app.core.config import Settings
from app.services.genai_verification import (
    GenAiVerificationService,
    MockGenAiVerificationClient,
)
from app.services.rag_ml_integration import RagDirectClient
from scripts.validate_uploaded_pdfs_be13 import (
    ValidationOptions,
    _packaging_safety,
    build_parser,
    check_real_rag_dependencies,
    configure_environment,
    find_unsupported_support_labels,
    install_deterministic_rag_probe,
    options_from_args,
    render_validation_report,
    restore_deterministic_rag_probe,
    validate_mode_preconditions,
)


def test_cli_help_documents_staged_validation_flags() -> None:
    help_text = build_parser().format_help()

    for flag in (
        "--mock-rag",
        "--real-rag",
        "--mock-genai",
        "--real-genai",
        "--metadata-disabled",
        "--metadata-mock",
        "--metadata-live",
        "--live-rag-embeddings",
        "--pdf-dir",
        "--report-output",
    ):
        assert flag in help_text
    assert "real RagDirectClient adapter" in help_text
    assert "deterministic Door 1" in help_text


def test_default_mode_preserves_mock_rag_and_mock_genai(monkeypatch) -> None:
    args = build_parser().parse_args([])
    options = options_from_args(args)

    environment = configure_environment(options)
    settings = Settings(**environment)

    assert options.retrieval_mode == "Mock RAG"
    assert options.verification_mode == "Mock GenAI"
    assert environment["RAG_MOCK_MODE"] == "true"
    assert environment["GENAI_MOCK_MODE"] == "true"
    assert settings.rag_mock_mode is True
    assert isinstance(
        GenAiVerificationService(settings=settings).client,
        MockGenAiVerificationClient,
    )


def test_real_rag_mock_genai_metadata_disabled_configures_safe_environment(
    monkeypatch,
) -> None:
    options = ValidationOptions(
        rag_mode="real",
        genai_mode="mock",
        metadata_mode="disabled",
    )

    environment = configure_environment(options)
    settings = Settings(**environment)

    assert environment == {
        "RAG_MOCK_MODE": "false",
        "GENAI_MOCK_MODE": "true",
        "METADATA_MOCK_MODE": "false",
        "METADATA_LOOKUP_ENABLED": "false",
    }
    assert settings.rag_mock_mode is False
    assert settings.genai_mock_mode is True
    assert settings.metadata_lookup_enabled is False
    assert isinstance(
        GenAiVerificationService(settings=settings).client,
        MockGenAiVerificationClient,
    )


def test_real_rag_mode_calls_real_direct_adapter_not_mock() -> None:
    probe = install_deterministic_rag_probe()
    try:
        result = RagDirectClient().retrieve(
            {
                "claim_id": "claim_validation",
                "reference_id": "reference_validation",
                "claim_text": "A deterministic validation claim.",
                "citation_text": "(Validation, 2026)",
                "doi": "10.0000/refcheck-staged-validation",
                "doi_status": "VALID",
                "source_evidence": {
                    "evidence_availability": "ABSTRACT_AVAILABLE",
                    "text": "Deterministic validation source text.",
                    "source_url": "https://doi.org/10.0000/refcheck-staged-validation",
                },
                "retrieval_options": {"top_k": 1},
            }
        )
    finally:
        restore_deterministic_rag_probe(probe)

    assert len(probe.calls) == 1
    assert probe.calls[0]["top_k"] == 1
    assert result.mock_mode is False
    assert result.payload["retrieval_status"] == "SUCCEEDED"
    assert len(result.payload["top_chunks"]) == 1
    assert result.payload["semantic_cache_match"] == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }


def test_missing_real_rag_dependency_reports_blocked() -> None:
    def missing_importer(module_name: str):
        if module_name == "rag.api":
            raise ModuleNotFoundError("No module named 'rag'")
        return object()

    dependencies_available, error = check_real_rag_dependencies(missing_importer)
    ready, reason = validate_mode_preconditions(
        ValidationOptions(rag_mode="real"),
        dependencies_available=dependencies_available,
        dependency_error=error,
    )

    assert dependencies_available is False
    assert ready is False
    assert "Real RAG dependencies are unavailable" in str(reason)
    assert "ModuleNotFoundError" in str(reason)


def test_live_modes_are_optional_and_key_guarded(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    rag_ready, rag_reason = validate_mode_preconditions(
        ValidationOptions(rag_mode="real", live_rag_embeddings=True),
        dependencies_available=True,
        dependency_error=None,
    )
    genai_ready, genai_reason = validate_mode_preconditions(
        ValidationOptions(rag_mode="real", genai_mode="real"),
        dependencies_available=True,
        dependency_error=None,
    )

    assert rag_ready is False
    assert rag_reason == "Fully live RAG embeddings require OPENROUTER_API_KEY."
    assert genai_ready is False
    assert genai_reason == "Real GenAI is optional and requires OPENROUTER_API_KEY."


def test_summary_reports_all_mode_labels() -> None:
    report = render_validation_report(
        options=ValidationOptions(
            rag_mode="real",
            genai_mode="mock",
            metadata_mode="disabled",
        ),
        validation_status="PASS",
        results=[],
    )

    assert "retrieval_mode: Real RAG" in report
    assert "verification_mode: Mock GenAI" in report
    assert "metadata_mode: disabled" in report
    assert "real RagDirectClient adapter with deterministic Door 1 boundary" in report


def test_unsupported_support_labels_are_never_accepted() -> None:
    unsupported = find_unsupported_support_labels(
        [
            {"support_status": "SUPPORTED"},
            {"support_status": "VALIDATED"},
            {"support_status": "NEEDS_HUMAN_REVIEW"},
        ],
        allowed_statuses={
            "SUPPORTED",
            "PARTIALLY_SUPPORTED",
            "NOT_SUPPORTED",
            "INSUFFICIENT_EVIDENCE",
            "NEEDS_HUMAN_REVIEW",
        },
    )

    assert unsupported == ["VALIDATED"]


def test_packaging_scan_remains_clean_and_excludes_private_pdfs() -> None:
    safety = _packaging_safety()

    assert safety["packaging_safety_passed"] is True
    assert safety["packaging_unsafe_entries"] == []
    assert safety["packaging_forbidden_entries"] == []
    assert safety["packaging_pdf_entries"] == 0
