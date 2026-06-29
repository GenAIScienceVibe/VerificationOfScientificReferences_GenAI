from __future__ import annotations

from unittest.mock import Mock

from testsupport.api_client import ApiTestClient as TestClient
from sqlalchemy.orm import Session

from app.clients.metadata_clients import MetadataLookupResponse
from app.core.config import Settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Document, Reference, SourceMetadata
from app.models.enums import DocumentStatus, DoiStatus, MetadataStatus, UploadType
from app.services.doi_metadata_lookup import MetadataLookupService, is_valid_doi_syntax, normalize_doi_for_lookup
from app.services.metadata_scoring import calculate_metadata_match
from app.services.reference_extraction import ReferenceExtractionService

client = TestClient(app)


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert "message" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def create_reference(*, doi: str | None = "10.1234/demo.2024", title: str = "Demo Article", authors: str = "Smith, J.", year: int = 2024) -> str:
    with SessionLocal() as db:
        document = Document(
            filename="metadata-test.txt",
            title="Metadata Test",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.REFERENCES_EXTRACTED.value,
            raw_text="References\nSmith, J. (2024). Demo Article.",
            cleaned_text="References\nSmith, J. (2024). Demo Article.",
        )
        db.add(document)
        db.flush()
        reference = Reference(
            document_id=document.id,
            reference_key="Smith_2024",
            raw_reference="Smith, J. (2024). Demo Article. https://doi.org/10.1234/demo.2024",
            extracted_title=title,
            extracted_authors=authors,
            extracted_year=year,
            extracted_doi=doi,
            doi_status=DoiStatus.FOUND.value if doi else DoiStatus.MISSING.value,
            metadata_status=MetadataStatus.NOT_LOOKED_UP.value,
        )
        db.add(reference)
        db.commit()
        return reference.id


def crossref_success(self, doi: str) -> MetadataLookupResponse:  # noqa: ANN001 - monkeypatched bound method signature
    return MetadataLookupResponse(
        success=True,
        lookup_source="CrossRef",
        lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
        doi=doi,
        title="Demo Article",
        authors=["Jane Smith"],
        year=2024,
        venue="Journal of Demo Studies",
        publisher="Demo Publisher",
        abstract="This is an official abstract from the mocked CrossRef response.",
        url=f"https://doi.org/{doi}",
        raw_metadata_json={"message": {"DOI": doi, "title": ["Demo Article"]}},
        status_code=200,
    )


def crossref_not_found(self, doi: str) -> MetadataLookupResponse:  # noqa: ANN001
    return MetadataLookupResponse(
        success=False,
        lookup_source="CrossRef",
        lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
        doi=doi,
        status_code=404,
        error_code="METADATA_UNAVAILABLE",
        error_message="Not found",
    )


def crossref_timeout(self, doi: str) -> MetadataLookupResponse:  # noqa: ANN001
    return MetadataLookupResponse(
        success=False,
        lookup_source="CrossRef",
        lookup_status=MetadataStatus.LOOKUP_FAILED.value,
        doi=doi,
        error_code="METADATA_LOOKUP_TIMEOUT",
        error_message="Timeout",
    )


def metadata_disabled_service() -> tuple[MetadataLookupService, list[Mock]]:
    """Build a disabled service whose provider methods fail if invoked."""
    crossref = Mock(name="crossref")
    openalex = Mock(name="openalex")
    semantic_scholar = Mock(name="semantic_scholar")
    unpaywall = Mock(name="unpaywall")
    core = Mock(name="core")
    ssrn = Mock(name="ssrn")
    doi_resolver = Mock(name="doi_resolver")

    external_calls = [
        crossref.search_by_title,
        crossref.lookup_by_doi,
        openalex.search_by_title,
        openalex.lookup_by_doi,
        semantic_scholar.search_by_title,
        semantic_scholar.lookup_by_doi,
        semantic_scholar.lookup_by_arxiv_id,
        unpaywall.lookup_by_doi,
        core.search_by_title,
        core.get_fulltext_by_doi,
        ssrn.get_abstract_for_doi,
        doi_resolver.resolver_url,
    ]
    for provider_call in external_calls:
        provider_call.side_effect = AssertionError("External metadata provider was called while disabled")

    settings = Settings(
        METADATA_LOOKUP_ENABLED="false",
        CORE_API_KEY="disabled-mode-test-key",
        UNPAYWALL_EMAIL="disabled-mode@example.test",
    )
    service = MetadataLookupService(
        settings=settings,
        crossref_client=crossref,
        openalex_client=openalex,
        semantic_scholar_client=semantic_scholar,
        unpaywall_client=unpaywall,
        core_client=core,
        ssrn_client=ssrn,
        doi_resolver_client=doi_resolver,
    )
    return service, external_calls


def assert_no_external_calls(external_calls: list[Mock]) -> None:
    for provider_call in external_calls:
        provider_call.assert_not_called()


def test_be42_reference_splitting_regression_for_multiline_following_doi() -> None:
    service = ReferenceExtractionService()
    text = """
References
Smith, J. (2024). First article title. Journal of AI Learning, 4(1), 1-9.
https://doi.org/10.1234/first.article
Jones, A. (2023). Second article title without DOI.
"""
    section = service.find_reference_section(cleaned_text=text, sections=[])
    parsed = service.extract_references(section.text)
    assert len(parsed) == 2
    assert parsed[0].reference_key.startswith("Smith")
    assert parsed[0].extracted_doi == "10.1234/first.article"
    assert parsed[1].doi_status == DoiStatus.MISSING.value


def test_be42_orphan_doi_tail_is_not_attached_to_previous_reference() -> None:
    service = ReferenceExtractionService()
    text = """
References
Wang, X., Liu, Q., Pang, H., Tan, S. C., Lei, J., Wallace, M. P., & Li, L. (2023). What matters in AI-supported learning. Computers & Education, 194, Article 104703. https://doi.org/10.1016/j.compedu.2022.104703

https://doi.org/10.1177/00336882221094089
"""
    section = service.find_reference_section(cleaned_text=text, sections=[])
    parsed = service.extract_references(section.text)
    assert len(parsed) == 1
    assert parsed[0].extracted_doi == "10.1016/j.compedu.2022.104703"
    assert not any(item.raw_reference.startswith("Unattached DOI-only reference") for item in parsed)
    assert service.skipped_doi_fragments == ["10.1177/00336882221094089"]


def test_doi_normalization_supported_formats() -> None:
    examples = {
        "https://doi.org/10.1234/ABC.Def.2024.": "10.1234/abc.def.2024",
        "http://dx.doi.org/10.5678/DX.Value)": "10.5678/dx.value",
        "DOI: 10.9999/UPPER.CASE": "10.9999/upper.case",
        "doi:10.7777/trailing;": "10.7777/trailing",
    }
    for raw, expected in examples.items():
        assert normalize_doi_for_lookup(raw) == expected
        assert is_valid_doi_syntax(expected)
    assert not is_valid_doi_syntax(normalize_doi_for_lookup("doi:10.bad/value"))
    assert normalize_doi_for_lookup(None) is None


def test_metadata_scoring_high_and_low_match() -> None:
    high = calculate_metadata_match(
        extracted_title="AI Writing Assistants and Student Productivity",
        extracted_authors="Smith, J.",
        extracted_year=2023,
        extracted_doi="10.1234/ai.2023",
        metadata_title="AI Writing Assistants and Student Productivity",
        metadata_authors=["John Smith"],
        metadata_year=2023,
        metadata_doi="10.1234/ai.2023",
    )
    assert high.metadata_match_score and high.metadata_match_score > 0.90
    low = calculate_metadata_match(
        extracted_title="Completely Different Title",
        extracted_authors="Miller, A.",
        extracted_year=2020,
        extracted_doi="10.1234/wrong",
        metadata_title="AI Writing Assistants and Student Productivity",
        metadata_authors=["John Smith"],
        metadata_year=2023,
        metadata_doi="10.1234/ai.2023",
    )
    assert low.metadata_match_score is not None
    assert low.metadata_match_score < 0.40


def test_verify_single_reference_success_persists_metadata(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.metadata_clients.CrossrefClient.lookup_by_doi", crossref_success)
    reference_id = create_reference()
    response = client.post(f"/api/v1/references/{reference_id}/verify-doi")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    data = payload["data"]
    assert data["doi_status"] == DoiStatus.VALID.value
    assert data["metadata_status"] == MetadataStatus.LOOKUP_SUCCEEDED.value
    assert data["metadata"]["title"] == "Demo Article"
    assert data["metadata_match_score"] >= 0.75

    with SessionLocal() as db:
        metadata = db.query(SourceMetadata).filter(SourceMetadata.reference_id == reference_id).one()
        reference = db.get(Reference, reference_id)
        assert metadata.lookup_status == MetadataStatus.LOOKUP_SUCCEEDED.value
        assert reference.doi_status == DoiStatus.VALID.value
        assert reference.metadata_status == MetadataStatus.LOOKUP_SUCCEEDED.value


def test_verify_single_reference_missing_doi_returns_standard_error() -> None:
    reference_id = create_reference(doi=None)
    response = client.post(f"/api/v1/references/{reference_id}/verify-doi")
    assert response.status_code == 422
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "DOI_MISSING"


def test_verify_single_reference_not_found_and_metadata_missing_errors() -> None:
    response = client.post("/api/v1/references/ref_missing/verify-doi")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "REFERENCE_NOT_FOUND"

    reference_id = create_reference()
    metadata_response = client.get(f"/api/v1/references/{reference_id}/metadata")
    assert metadata_response.status_code == 404
    assert metadata_response.json()["errors"][0]["code"] == "METADATA_UNAVAILABLE"


def test_lookup_404_marks_reference_invalid(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.metadata_clients.CrossrefClient.lookup_by_doi", crossref_not_found)
    reference_id = create_reference()
    response = client.post(f"/api/v1/references/{reference_id}/verify-doi")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["doi_status"] == DoiStatus.INVALID.value
    assert data["metadata_status"] == MetadataStatus.METADATA_UNAVAILABLE.value


def test_lookup_timeout_marks_lookup_failed_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.metadata_clients.CrossrefClient.lookup_by_doi", crossref_timeout)
    reference_id = create_reference()
    response = client.post(f"/api/v1/references/{reference_id}/verify-doi")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["doi_status"] == DoiStatus.FOUND.value
    assert data["metadata_status"] == MetadataStatus.LOOKUP_FAILED.value


def test_document_level_verify_dois_summary_and_get_metadata(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.metadata_clients.CrossrefClient.lookup_by_doi", crossref_success)
    with SessionLocal() as db:
        document = Document(
            filename="doc-level.txt",
            title="Doc Level",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.REFERENCES_EXTRACTED.value,
        )
        db.add(document)
        db.flush()
        ref1 = Reference(
            document_id=document.id,
            reference_key="Smith_2024",
            raw_reference="Smith, J. (2024). Demo Article. https://doi.org/10.1234/demo.2024",
            extracted_title="Demo Article",
            extracted_authors="Smith, J.",
            extracted_year=2024,
            extracted_doi="10.1234/demo.2024",
            doi_status=DoiStatus.FOUND.value,
            metadata_status=MetadataStatus.NOT_LOOKED_UP.value,
        )
        ref2 = Reference(
            document_id=document.id,
            reference_key="NoDoi_2024",
            raw_reference="NoDoi, N. (2024). Missing DOI.",
            extracted_title="Missing DOI",
            extracted_authors="NoDoi, N.",
            extracted_year=2024,
            extracted_doi=None,
            doi_status=DoiStatus.MISSING.value,
            metadata_status=MetadataStatus.NOT_LOOKED_UP.value,
        )
        db.add_all([ref1, ref2])
        db.commit()
        document_id = document.id
        ref1_id = ref1.id

    response = client.post(f"/api/v1/documents/{document_id}/verify-dois")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["total_references"] == 2
    assert payload["data"]["valid_dois"] == 1
    assert payload["data"]["missing_dois"] == 1
    assert payload["data"]["metadata_succeeded"] == 1

    refs_response = client.get(f"/api/v1/documents/{document_id}/references", params={"metadata_status": "LOOKUP_SUCCEEDED"})
    assert refs_response.status_code == 200
    assert refs_response.json()["data"]["total"] == 1

    metadata_response = client.get(f"/api/v1/references/{ref1_id}/metadata")
    assert metadata_response.status_code == 200
    assert metadata_response.json()["data"]["metadata"]["publisher"] == "Demo Publisher"


def test_metadata_cache_reuse_for_same_doi(monkeypatch) -> None:
    calls = {"count": 0}

    def counted_success(self, doi: str) -> MetadataLookupResponse:  # noqa: ANN001
        calls["count"] += 1
        return crossref_success(self, doi)

    monkeypatch.setattr("app.clients.metadata_clients.CrossrefClient.lookup_by_doi", counted_success)
    ref1 = create_reference(doi="10.1234/cache.test")
    ref2 = create_reference(doi="10.1234/cache.test", title="Demo Article")
    assert client.post(f"/api/v1/references/{ref1}/verify-doi").status_code == 200
    assert client.post(f"/api/v1/references/{ref2}/verify-doi").status_code == 200
    assert calls["count"] == 1


def test_metadata_disabled_blocks_all_providers_for_reference_with_doi(monkeypatch) -> None:
    service, external_calls = metadata_disabled_service()
    pdf_download = Mock(side_effect=AssertionError("External PDF download was called while disabled"))
    monkeypatch.setattr("app.services.doi_metadata_lookup._extract_fulltext_from_url", pdf_download)
    reference_id = create_reference(doi="10.1234/disabled.mode")

    with SessionLocal() as db:
        reference = db.get(Reference, reference_id)
        result = service.verify_document_dois(reference.document_id, db)
        db.refresh(reference)

        assert result["lookup_failed"] == 1
        assert result["errors"][0]["code"] == "METADATA_SERVICE_UNAVAILABLE"
        assert reference.doi_status == DoiStatus.FOUND.value
        assert reference.metadata_status == MetadataStatus.LOOKUP_FAILED.value

    assert_no_external_calls(external_calls)
    pdf_download.assert_not_called()


def test_metadata_disabled_blocks_title_and_all_providers_for_missing_doi(monkeypatch) -> None:
    service, external_calls = metadata_disabled_service()
    pdf_download = Mock(side_effect=AssertionError("External PDF download was called while disabled"))
    monkeypatch.setattr("app.services.doi_metadata_lookup._extract_fulltext_from_url", pdf_download)
    reference_id = create_reference(doi=None, title="A title that must not be searched")

    with SessionLocal() as db:
        reference = db.get(Reference, reference_id)
        result = service.verify_document_dois(reference.document_id, db)
        db.refresh(reference)
        metadata = db.query(SourceMetadata).filter(SourceMetadata.reference_id == reference_id).one()

        assert result["missing_dois"] == 1
        assert result["metadata_unavailable"] == 1
        assert result["errors"] == []
        assert reference.doi_status == DoiStatus.MISSING.value
        assert reference.metadata_status == MetadataStatus.METADATA_UNAVAILABLE.value
        assert metadata.raw_metadata_json == {"reason": "missing_doi"}

    assert_no_external_calls(external_calls)
    pdf_download.assert_not_called()
