from __future__ import annotations

from pathlib import Path

from testsupport.api_client import ApiTestClient as TestClient

from app.main import app
from app.models.enums import DoiStatus, MetadataStatus
from app.services.reference_extraction import ReferenceExtractionService
from app.services.text_processing import clean_text

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def assert_wrapper(payload: dict, success: bool = True) -> None:
    assert payload["success"] is success
    assert "data" in payload
    assert "message" in payload
    assert isinstance(payload["errors"], list)
    assert payload["request_id"].startswith("req_")


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def create_text_document(text: str, title: str = "Reference Test") -> str:
    response = client.post("/api/v1/documents/text", json={"title": title, "text": text})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    return payload["data"]["document_id"]


def test_reference_section_detection_supports_references_and_bibliography_and_appendix_stop() -> None:
    service = ReferenceExtractionService()
    text = clean_text(
        "Paper\n\nBody\nContent.\n\nBibliography\nSmith, J. (2023). Demo. doi:10.1234/demo.2023\n\nAppendix\nDo not include this."
    )
    result = service.find_reference_section(cleaned_text=text, sections=[])
    assert "Smith, J." in result.text
    assert "Do not include" not in result.text


def test_reference_section_detection_missing_section_raises_project_error() -> None:
    service = ReferenceExtractionService()
    try:
        service.find_reference_section(cleaned_text=read_fixture("sample_text_without_references.txt"), sections=[])
    except Exception as exc:
        assert getattr(exc, "error").code == "REFERENCE_SECTION_NOT_FOUND"
    else:  # pragma: no cover
        raise AssertionError("Expected reference section error")


def test_reference_splitting_supports_apa_numbered_bracketed_and_multiline_references() -> None:
    service = ReferenceExtractionService()
    numbered_text = clean_text(read_fixture("sample_text_with_numbered_references.txt"))
    section = service.find_reference_section(cleaned_text=numbered_text, sections=[])
    references = service.split_references(section.text)
    assert len(references) == 3
    assert references[0].startswith("[1]")
    assert "continues on the next line" in references[1]
    assert references[2].startswith("3.")


def test_doi_extraction_normalizes_supported_formats_and_trailing_punctuation() -> None:
    service = ReferenceExtractionService()
    examples = {
        "Smith (2023). 10.1234/ABC.Def.2023.": "10.1234/abc.def.2023",
        "Smith (2023). doi:10.5678/Prefix.DOI": "10.5678/prefix.doi",
        "Smith (2023). DOI: 10.5678/Prefix.DOI": "10.5678/prefix.doi",
        "Smith (2023). https://doi.org/10.9999/URL.DOI.2021.": "10.9999/url.doi.2021",
        "Smith (2023). http://dx.doi.org/10.8888/DX.DOI.2021)": "10.8888/dx.doi.2021",
    }
    for raw, expected in examples.items():
        result = service.extract_doi(raw)
        assert result.doi_status == DoiStatus.FOUND.value
        assert result.extracted_doi == expected


def test_doi_extraction_handles_missing_and_malformed() -> None:
    service = ReferenceExtractionService()
    assert service.extract_doi("Smith, J. (2023). No DOI here.").doi_status == DoiStatus.MISSING.value
    malformed = service.extract_doi("Smith, J. (2023). Broken DOI: 10.abc/bad")
    assert malformed.doi_status == DoiStatus.MALFORMED.value


def test_extract_references_api_persists_references_and_updates_document_status() -> None:
    document_id = create_text_document(read_fixture("sample_text_with_apa_references.txt"))

    response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["document_id"] == document_id
    assert payload["data"]["references_count"] == 3
    assert payload["data"]["doi_summary"]["found"] == 2
    assert payload["data"]["doi_summary"]["missing"] == 1
    assert payload["data"]["status"] == "REFERENCES_EXTRACTED"

    status_response = client.get(f"/api/v1/documents/{document_id}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["data"]["status"] == "REFERENCES_EXTRACTED"
    assert status_payload["data"]["progress_percentage"] == 45

    refs_response = client.get(f"/api/v1/documents/{document_id}/references")
    assert refs_response.status_code == 200
    refs_payload = refs_response.json()
    assert_wrapper(refs_payload)
    assert refs_payload["data"]["total"] == 3
    references = refs_payload["data"]["references"]
    # DB ordering is not guaranteed when created_at timestamps are identical — find by DOI
    smith = next(r for r in references if r.get("extracted_doi") == "10.1234/abc.def.2023")
    assert smith["metadata_status"] == MetadataStatus.NOT_LOOKED_UP.value
    assert smith["doi_status"] == DoiStatus.FOUND.value

    single_response = client.get(f"/api/v1/references/{smith['reference_id']}")
    assert single_response.status_code == 200
    assert single_response.json()["data"]["reference_id"] == smith["reference_id"]


def test_extract_references_skips_unattached_doi_only_fragment_with_quality_warning() -> None:
    document_id = create_text_document(
        """
Sample Paper

Body
Demo body.

References
Wang, X., Liu, Q., Pang, H., Tan, S. C., Lei, J., Wallace, M. P., & Li, L. (2023). What matters in AI-supported learning. Computers & Education, 194, Article 104703. https://doi.org/10.1016/j.compedu.2022.104703

https://doi.org/10.1177/00336882221094089
""",
        title="Unattached DOI Fragment",
    )

    response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["references_count"] == 1
    assert payload["data"]["doi_summary"]["found"] == 1
    assert "UNATTACHED_DOI_FRAGMENT_SKIPPED" in payload["data"]["quality_warnings"]
    assert "10.1177/00336882221094089" in payload["data"]["doi_coverage"]["missing_from_extracted"]

    refs_response = client.get(f"/api/v1/documents/{document_id}/references")
    assert refs_response.status_code == 200
    references = refs_response.json()["data"]["references"]
    assert len(references) == 1
    assert references[0]["extracted_doi"] == "10.1016/j.compedu.2022.104703"
    assert "Unattached DOI-only reference" not in references[0]["raw_reference"]
    assert "10.1177/00336882221094089" not in references[0]["raw_reference"]


def test_extract_references_is_idempotent_and_does_not_duplicate_records() -> None:
    document_id = create_text_document(read_fixture("sample_text_with_apa_references.txt"))
    first_response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    second_response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert first_response.status_code == 200
    assert second_response.status_code == 200

    refs_response = client.get(f"/api/v1/documents/{document_id}/references")
    payload = refs_response.json()
    assert payload["data"]["total"] == 3


def test_get_references_supports_doi_status_filter() -> None:
    document_id = create_text_document(read_fixture("sample_text_with_apa_references.txt"))
    client.post(f"/api/v1/documents/{document_id}/extract-references")

    response = client.get(f"/api/v1/documents/{document_id}/references", params={"doi_status": "MISSING"})
    assert response.status_code == 200
    payload = response.json()
    assert_wrapper(payload)
    assert payload["data"]["total"] == 1
    assert payload["data"]["references"][0]["doi_status"] == "MISSING"


def test_extract_references_for_missing_document_returns_standard_error() -> None:
    response = client.post("/api/v1/documents/doc_missing/extract-references")
    assert response.status_code == 404
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "DOCUMENT_NOT_FOUND"


def test_extract_references_without_text_returns_standard_error() -> None:
    response = client.post("/api/v1/documents/text", json={"title": "No Refs", "text": read_fixture("sample_text_without_references.txt")})
    assert response.status_code == 200
    document_id = response.json()["data"]["document_id"]

    extract_response = client.post(f"/api/v1/documents/{document_id}/extract-references")
    assert extract_response.status_code == 422
    payload = extract_response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "REFERENCE_SECTION_NOT_FOUND"


def test_missing_reference_returns_standard_error_wrapper() -> None:
    response = client.get("/api/v1/references/ref_missing")
    assert response.status_code == 404
    payload = response.json()
    assert_wrapper(payload, success=False)
    assert payload["errors"][0]["code"] == "REFERENCE_NOT_FOUND"


def test_text_cleaning_does_not_destroy_dois_before_reference_extraction() -> None:
    cleaned = clean_text(read_fixture("sample_references_with_dois.txt"))
    assert "10.1234/plain.doi" in cleaned
    assert "doi:10.5678/prefix.doi" in cleaned
    parsed = ReferenceExtractionService().extract_references(cleaned)
    assert len(parsed) == 4
    assert [item.doi_status for item in parsed].count(DoiStatus.FOUND.value) == 3
    assert [item.doi_status for item in parsed].count(DoiStatus.MALFORMED.value) == 1
