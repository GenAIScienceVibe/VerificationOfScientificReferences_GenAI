from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock

import pytest
from testsupport.api_client import ApiTestClient as TestClient

import app.services.doi_metadata_lookup as metadata_lookup_module
from app.clients.metadata_clients import MetadataLookupResponse
from app.core.config import Settings
from app.core.errors import AppException
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Citation,
    Claim,
    ClaimReferenceLink,
    Document,
    EvidencePackage,
    RagRetrievalResult,
    Reference,
    SourceMetadata,
)
from app.models.enums import (
    DocumentStatus,
    DoiStatus,
    EvidenceAvailability,
    MappingStatus,
    MetadataStatus,
    RetrievalStatus,
    UploadType,
)
from app.services.doi_metadata_lookup import (
    MetadataLookupService,
    _extract_fulltext_from_bytes,
)
from app.services.evidence_package_builder import EvidencePackageBuilder
from app.services.rag_ml_integration import (
    RagDirectClient,
    RagMlClient,
    RagRequestBuilder,
    RagRetrievalService,
)


client = TestClient(app)
FULL_TEXT = (
    "The controlled study found that the intervention improved reproducibility. "
    "Methods, results, and limitations are included in this deterministic text."
)
ABSTRACT = "The controlled study reports a reproducibility improvement."
PUBLIC_SOURCE_URL = "https://repository.example.test/articles/reproducibility.pdf"
PRIVATE_PATH_MARKERS = ("/home/", "/Users/", "C:\\Users\\", "file://")


@dataclass(frozen=True)
class PipelineIds:
    document_id: str
    claim_id: str
    reference_id: str


def _create_linked_reference(
    *,
    doi: str = "10.1234/fulltext.demo",
    title: str = "A Reproducibility Study",
    year: int = 2024,
    with_metadata: bool = False,
    metadata_url: str = PUBLIC_SOURCE_URL,
    abstract: str | None = ABSTRACT,
) -> PipelineIds:
    with SessionLocal() as db:
        document = Document(
            filename="full-text-test.txt",
            title="Full-text Pipeline Test",
            upload_type=UploadType.TEXT.value,
            status=DocumentStatus.CLAIMS_EXTRACTED.value,
        )
        db.add(document)
        db.flush()
        reference = Reference(
            document_id=document.id,
            reference_key="Researcher_2024",
            raw_reference=(
                f"Researcher, A. ({year}). {title}. https://doi.org/{doi}"
            ),
            extracted_title=title,
            extracted_authors="Researcher, A.",
            extracted_year=year,
            extracted_doi=doi,
            doi_status=(
                DoiStatus.VALID.value if with_metadata else DoiStatus.FOUND.value
            ),
            metadata_status=(
                MetadataStatus.LOOKUP_SUCCEEDED.value
                if with_metadata
                else MetadataStatus.NOT_LOOKED_UP.value
            ),
            metadata_match_score=0.96 if with_metadata else None,
        )
        claim = Claim(
            document_id=document.id,
            claim_text="The intervention improved reproducibility.",
            claim_type="EMPIRICAL",
            section_name="Results",
            source_paragraph=(
                "The intervention improved reproducibility (Researcher, 2024)."
            ),
            paragraph_index=1,
            sentence_index=0,
            extraction_confidence=0.95,
        )
        db.add_all([reference, claim])
        db.flush()
        citation = Citation(
            document_id=document.id,
            claim_id=claim.id,
            raw_citation="(Researcher, 2024)",
            citation_style="APA",
            sentence_text=claim.source_paragraph,
            mapped_reference_id=reference.id,
            mapping_confidence=0.97,
        )
        db.add(citation)
        db.flush()
        db.add(
            ClaimReferenceLink(
                document_id=document.id,
                claim_id=claim.id,
                citation_id=citation.id,
                reference_id=reference.id,
                mapping_status=MappingStatus.MAPPED.value,
                mapping_confidence=0.97,
                mapping_reason="Author and year match.",
            )
        )
        if with_metadata:
            db.add(
                SourceMetadata(
                    reference_id=reference.id,
                    doi=doi,
                    title=title,
                    authors="A. Researcher",
                    year=year,
                    venue="Journal of Reproducible Tests",
                    publisher="Example Publisher",
                    abstract=abstract,
                    url=metadata_url,
                    lookup_source="CrossRef",
                    lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                    raw_metadata_json={"provider": "deterministic-test"},
                    metadata_match_score=0.96,
                    title_match=1.0,
                    author_match=1.0,
                    year_match=True,
                    doi_match=True,
                )
            )
        db.commit()
        return PipelineIds(document.id, claim.id, reference.id)


def _crossref_success(
    doi: str,
    *,
    abstract: str | None = ABSTRACT,
    url: str | None = None,
) -> MetadataLookupResponse:
    return MetadataLookupResponse(
        success=True,
        lookup_source="CrossRef",
        lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
        doi=doi,
        title="A Reproducibility Study",
        authors=["A. Researcher"],
        year=2024,
        venue="Journal of Reproducible Tests",
        publisher="Example Publisher",
        abstract=abstract,
        url=url or f"https://doi.org/{doi}",
        raw_metadata_json={"provider": "crossref-test"},
        status_code=200,
    )


def _missing_response(source: str, doi: str) -> MetadataLookupResponse:
    return MetadataLookupResponse(
        success=False,
        lookup_source=source,
        lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
        doi=doi,
        status_code=404,
        error_code="METADATA_UNAVAILABLE",
        error_message=f"{source} returned no result.",
    )


def _metadata_service(
    *,
    settings: Settings,
    crossref_response: MetadataLookupResponse,
) -> tuple[MetadataLookupService, dict[str, Mock]]:
    providers = {
        "crossref": Mock(name="crossref"),
        "openalex": Mock(name="openalex"),
        "semantic_scholar": Mock(name="semantic_scholar"),
        "unpaywall": Mock(name="unpaywall"),
        "core": Mock(name="core"),
        "ssrn": Mock(name="ssrn"),
        "doi_resolver": Mock(name="doi_resolver"),
    }
    providers["crossref"].lookup_by_doi.return_value = crossref_response
    providers["doi_resolver"].resolver_url.side_effect = (
        lambda doi: f"https://doi.org/{doi}"
    )
    service = MetadataLookupService(
        settings=settings,
        crossref_client=providers["crossref"],
        openalex_client=providers["openalex"],
        semantic_scholar_client=providers["semantic_scholar"],
        unpaywall_client=providers["unpaywall"],
        core_client=providers["core"],
        ssrn_client=providers["ssrn"],
        doi_resolver_client=providers["doi_resolver"],
    )
    return service, providers


def _lookup_and_prepare(
    service: MetadataLookupService,
    ids: PipelineIds,
) -> dict[str, Any]:
    with SessionLocal() as db:
        service.verify_reference_doi(ids.reference_id, db, force_refresh=True)
        prepared = EvidencePackageBuilder().prepare_evidence_for_document(
            ids.document_id,
            db,
        )
        metadata = (
            db.query(SourceMetadata)
            .filter(SourceMetadata.reference_id == ids.reference_id)
            .one()
        )
        package = (
            db.query(EvidencePackage)
            .filter(EvidencePackage.document_id == ids.document_id)
            .one()
        )
        return {
            "prepared": dict(prepared),
            "raw_metadata": dict(metadata.raw_metadata_json or {}),
            "metadata_url": metadata.url,
            "metadata_abstract": metadata.abstract,
            "lookup_source": metadata.lookup_source,
            "availability": package.evidence_availability,
            "evidence_text": package.source_evidence_text,
            "source_url": package.source_url,
            "warnings": list(package.package_warnings_json or []),
            "package_id": package.id,
        }


def _assert_no_private_path(value: Any) -> None:
    serialized = str(value)
    assert not any(marker in serialized for marker in PRIVATE_PATH_MARKERS)


def test_uploaded_source_pdf_flows_to_full_text_evidence_and_real_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _create_linked_reference(with_metadata=True)
    extraction_call: dict[str, Any] = {}

    def fake_extract(pdf_bytes: bytes, *, max_chars: int) -> str:
        extraction_call["bytes"] = pdf_bytes
        extraction_call["max_chars"] = max_chars
        return FULL_TEXT

    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_bytes",
        fake_extract,
    )
    response = client.post(
        f"/api/v1/references/{ids.reference_id}/upload-source-pdf",
        files={"file": ("synthetic-source.pdf", b"mock-pdf-bytes", "application/pdf")},
    )

    assert response.status_code == 200
    upload = response.json()
    assert upload["success"] is True
    assert upload["data"]["reference_id"] == ids.reference_id
    assert upload["data"]["chars_extracted"] == len(FULL_TEXT)
    assert upload["data"]["affected_claims_count"] == 1
    assert extraction_call == {
        "bytes": b"mock-pdf-bytes",
        "max_chars": Settings().fulltext_max_chars,
    }

    with SessionLocal() as db:
        metadata = (
            db.query(SourceMetadata)
            .filter(SourceMetadata.reference_id == ids.reference_id)
            .one()
        )
        reference = db.get(Reference, ids.reference_id)
        assert metadata.raw_metadata_json["full_text"] == FULL_TEXT
        assert (
            metadata.raw_metadata_json["full_text_source"]
            == "user_upload:synthetic-source.pdf"
        )
        assert reference.metadata_status == MetadataStatus.LOOKUP_SUCCEEDED.value

    prepared_response = client.post(
        f"/api/v1/documents/{ids.document_id}/prepare-evidence"
    )
    assert prepared_response.status_code == 200
    assert prepared_response.json()["data"]["full_text_available"] == 1

    with SessionLocal() as db:
        package = (
            db.query(EvidencePackage)
            .filter(EvidencePackage.document_id == ids.document_id)
            .one()
        )
        assert package.evidence_availability == EvidenceAvailability.FULL_TEXT_AVAILABLE.value
        assert package.source_evidence_text == FULL_TEXT
        request_payload = RagRequestBuilder().build(package, top_k=2)
        package_id = package.id

    assert request_payload["source_evidence"] == {
        "evidence_availability": EvidenceAvailability.FULL_TEXT_AVAILABLE.value,
        "text": FULL_TEXT,
        "source_url": PUBLIC_SOURCE_URL,
    }
    _assert_no_private_path(request_payload)

    direct_client = RagDirectClient()
    import rag.api as rag_api

    captured: dict[str, Any] = {}

    def fake_retrieve(request):
        captured["request"] = request
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.SUCCEEDED,
            top_chunks=[
                rag_api.TopChunkResult(
                    chunk_id="full_text_chunk_1",
                    chunk_text="The controlled study found improved reproducibility.",
                    similarity_score=0.91,
                    evidence_type="FULL_TEXT",
                )
            ],
            overall_similarity_score=0.91,
            retrieval_confidence=0.89,
        )

    monkeypatch.setattr(rag_api, "retrieve_evidence", fake_retrieve)
    rag_settings = Settings(RAG_MOCK_MODE=False, RAG_SERVICE_ENABLED=True)
    rag_client = RagMlClient(
        settings=rag_settings,
        direct_client=direct_client,
    )

    with SessionLocal() as db:
        result = RagRetrievalService(
            settings=rag_settings,
            rag_client=rag_client,
        ).retrieve_evidence_for_claim(
            ids.claim_id,
            db,
            evidence_package_id=package_id,
            top_k=2,
            use_mock=False,
        )
        stored = (
            db.query(RagRetrievalResult)
            .filter(RagRetrievalResult.claim_id == ids.claim_id)
            .one()
        )

        assert result["retrieval_status"] == RetrievalStatus.SUCCEEDED.value
        assert result["top_chunks"][0]["evidence_type"] == "FULL_TEXT"
        assert result["top_chunks"][0]["source"] == "uploaded_full_text"
        assert result["top_chunks"][0]["source_url"] == PUBLIC_SOURCE_URL
        assert result["semantic_cache_match"] == {
            "matched": False,
            "cached_result_id": None,
            "similarity": None,
        }
        assert stored.top_chunks_json[0]["evidence_type"] == "FULL_TEXT"
        assert stored.top_chunks_json[0]["source"] == "uploaded_full_text"
        assert stored.top_chunks_json[0]["source_url"] == PUBLIC_SOURCE_URL
        assert stored.response_payload_json["mock_mode"] is False
        assert stored.error_message is None
        assert "support_status" not in stored.response_payload_json
        _assert_no_private_path(stored.top_chunks_json)
        _assert_no_private_path(stored.response_payload_json)

    rag_request = captured["request"]
    assert rag_request.source_evidence.evidence_availability.value == "FULL_TEXT_AVAILABLE"
    assert rag_request.source_evidence.text == FULL_TEXT
    assert rag_request.source_evidence.source_url == PUBLIC_SOURCE_URL
    assert rag_request.top_k == 2


def test_uploaded_pdf_text_extraction_honors_character_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePage:
        def get_text(self) -> str:
            return "abcdefghijklmnopqrstuvwxyz"

    class FakeDocument:
        closed = False

        def __iter__(self):
            return iter([FakePage(), FakePage()])

        def close(self) -> None:
            self.closed = True

    document = FakeDocument()
    monkeypatch.setattr(
        metadata_lookup_module.pymupdf,
        "open",
        lambda **_kwargs: document,
    )

    extracted = _extract_fulltext_from_bytes(b"synthetic", max_chars=20)

    assert extracted == "abcdefghijklmnopqrst"
    assert len(extracted) == 20
    assert document.closed is True


def test_unpaywall_pdf_success_builds_full_text_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.1234/unpaywall.demo"
    ids = _create_linked_reference(doi=doi)
    service, providers = _metadata_service(
        settings=Settings(
            METADATA_LOOKUP_ENABLED=True,
            UNPAYWALL_EMAIL="qa@example.test",
        ),
        crossref_response=_crossref_success(doi),
    )
    providers["unpaywall"].lookup_by_doi.return_value = PUBLIC_SOURCE_URL
    pdf_extract = Mock(return_value=FULL_TEXT)
    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_url",
        pdf_extract,
    )

    snapshot = _lookup_and_prepare(service, ids)

    providers["unpaywall"].lookup_by_doi.assert_called_once_with(doi)
    providers["core"].get_fulltext_by_doi.assert_not_called()
    pdf_extract.assert_called_once_with(
        PUBLIC_SOURCE_URL,
        max_bytes=service.settings.fulltext_max_bytes,
        max_chars=service.settings.fulltext_max_chars,
    )
    assert snapshot["raw_metadata"]["full_text"] == FULL_TEXT
    assert snapshot["raw_metadata"]["full_text_source"] == PUBLIC_SOURCE_URL
    assert snapshot["availability"] == EvidenceAvailability.FULL_TEXT_AVAILABLE.value
    assert snapshot["evidence_text"] == FULL_TEXT
    assert snapshot["source_url"] == PUBLIC_SOURCE_URL


def test_arxiv_pdf_success_builds_full_text_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.48550/arxiv.2405.15561"
    arxiv_url = "https://arxiv.org/pdf/2405.15561"
    ids = _create_linked_reference(doi=doi)
    service, providers = _metadata_service(
        settings=Settings(
            METADATA_LOOKUP_ENABLED=True,
            UNPAYWALL_EMAIL="qa@example.test",
        ),
        crossref_response=_crossref_success(doi),
    )
    pdf_extract = Mock(return_value=FULL_TEXT)
    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_url",
        pdf_extract,
    )

    snapshot = _lookup_and_prepare(service, ids)

    providers["unpaywall"].lookup_by_doi.assert_not_called()
    pdf_extract.assert_called_once_with(
        arxiv_url,
        max_bytes=service.settings.fulltext_max_bytes,
        max_chars=service.settings.fulltext_max_chars,
    )
    assert snapshot["raw_metadata"]["full_text"] == FULL_TEXT
    assert snapshot["raw_metadata"]["full_text_source"] == arxiv_url
    assert snapshot["availability"] == EvidenceAvailability.FULL_TEXT_AVAILABLE.value
    assert snapshot["source_url"] == arxiv_url


def test_core_inline_full_text_success_builds_full_text_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.1234/core.demo"
    core_url = "https://core.example.test/works/core-demo"
    ids = _create_linked_reference(doi=doi)
    service, providers = _metadata_service(
        settings=Settings(
            METADATA_LOOKUP_ENABLED=True,
            CORE_API_KEY="deterministic-test-key",
        ),
        crossref_response=_crossref_success(doi),
    )
    providers["core"].get_fulltext_by_doi.return_value = (FULL_TEXT, core_url)
    pdf_extract = Mock(
        side_effect=AssertionError("Inline CORE text must not download a PDF")
    )
    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_url",
        pdf_extract,
    )

    snapshot = _lookup_and_prepare(service, ids)

    providers["core"].get_fulltext_by_doi.assert_called_once_with(doi)
    pdf_extract.assert_not_called()
    assert snapshot["raw_metadata"]["full_text"] == FULL_TEXT
    assert snapshot["raw_metadata"]["full_text_source"] == core_url
    assert snapshot["availability"] == EvidenceAvailability.FULL_TEXT_AVAILABLE.value
    assert snapshot["source_url"] == core_url


def test_provider_full_text_failures_fall_back_to_abstract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.1234/provider-failure.demo"
    ids = _create_linked_reference(doi=doi)
    service, providers = _metadata_service(
        settings=Settings(
            METADATA_LOOKUP_ENABLED=True,
            UNPAYWALL_EMAIL="qa@example.test",
            CORE_API_KEY="deterministic-test-key",
        ),
        crossref_response=_crossref_success(doi),
    )
    providers["unpaywall"].lookup_by_doi.return_value = PUBLIC_SOURCE_URL
    providers["core"].get_fulltext_by_doi.return_value = (None, None)
    pdf_extract = Mock(return_value=None)
    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_url",
        pdf_extract,
    )

    snapshot = _lookup_and_prepare(service, ids)

    providers["unpaywall"].lookup_by_doi.assert_called_once_with(doi)
    providers["core"].get_fulltext_by_doi.assert_called_once_with(doi)
    pdf_extract.assert_called_once()
    assert "full_text" not in snapshot["raw_metadata"]
    assert snapshot["metadata_abstract"] == ABSTRACT
    assert snapshot["availability"] == EvidenceAvailability.ABSTRACT_AVAILABLE.value
    assert snapshot["evidence_text"] == ABSTRACT


def test_metadata_disabled_blocks_all_provider_and_full_text_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.1234/disabled-fulltext.demo"
    ids = _create_linked_reference(doi=doi)
    service, providers = _metadata_service(
        settings=Settings(
            METADATA_LOOKUP_ENABLED=False,
            UNPAYWALL_EMAIL="qa@example.test",
            CORE_API_KEY="deterministic-test-key",
        ),
        crossref_response=_crossref_success(doi),
    )
    provider_calls = [
        providers["crossref"].lookup_by_doi,
        providers["crossref"].search_by_title,
        providers["openalex"].lookup_by_doi,
        providers["openalex"].search_by_title,
        providers["semantic_scholar"].lookup_by_doi,
        providers["semantic_scholar"].lookup_by_arxiv_id,
        providers["semantic_scholar"].search_by_title,
        providers["unpaywall"].lookup_by_doi,
        providers["core"].get_fulltext_by_doi,
        providers["core"].search_by_title,
        providers["ssrn"].get_abstract_for_doi,
        providers["doi_resolver"].resolver_url,
    ]
    for provider_call in provider_calls:
        provider_call.side_effect = AssertionError(
            "External provider was called while metadata lookup was disabled"
        )
    pdf_extract = Mock(
        side_effect=AssertionError(
            "External full-text download was called while metadata lookup was disabled"
        )
    )
    monkeypatch.setattr(
        metadata_lookup_module,
        "_extract_fulltext_from_url",
        pdf_extract,
    )

    with SessionLocal() as db, pytest.raises(AppException) as exc:
        service.verify_reference_doi(ids.reference_id, db, force_refresh=True)

    assert exc.value.error.code == "METADATA_SERVICE_UNAVAILABLE"
    for provider_call in provider_calls:
        provider_call.assert_not_called()
    pdf_extract.assert_not_called()


def test_ssrn_preprint_is_retrieval_usable_without_final_support_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doi = "10.2139/ssrn.2803610"
    ssrn_url = "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2803610"
    preprint_abstract = "This preprint studies peer effects in acquisition decisions."
    ids = _create_linked_reference(doi=doi, title="An SSRN Working Paper", year=2016)
    service, providers = _metadata_service(
        settings=Settings(METADATA_LOOKUP_ENABLED=True),
        crossref_response=_crossref_success(doi, abstract=None, url=ssrn_url),
    )
    providers["openalex"].lookup_by_doi.return_value = _missing_response(
        "OpenAlex", doi
    )
    providers["semantic_scholar"].lookup_by_doi.return_value = _missing_response(
        "SemanticScholar", doi
    )
    providers["ssrn"].get_abstract_for_doi.return_value = preprint_abstract

    snapshot = _lookup_and_prepare(service, ids)

    assert snapshot["availability"] == EvidenceAvailability.PREPRINT_AVAILABLE.value
    assert snapshot["evidence_text"] == preprint_abstract
    assert any(item["code"] == "PREPRINT_SOURCE" for item in snapshot["warnings"])

    with SessionLocal() as db:
        package = db.get(EvidencePackage, snapshot["package_id"])
        request_payload = RagRequestBuilder().build(package, top_k=1)

    assert request_payload["source_evidence"] == {
        "evidence_availability": EvidenceAvailability.ABSTRACT_AVAILABLE.value,
        "text": preprint_abstract,
        "source_url": ssrn_url,
    }

    direct_client = RagDirectClient()
    import rag.api as rag_api

    def fake_retrieve(request):
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.SUCCEEDED,
            top_chunks=[
                rag_api.TopChunkResult(
                    chunk_id="preprint_chunk_1",
                    chunk_text=preprint_abstract,
                    similarity_score=0.84,
                    evidence_type="ABSTRACT",
                )
            ],
            overall_similarity_score=0.84,
            retrieval_confidence=0.84,
        )

    monkeypatch.setattr(rag_api, "retrieve_evidence", fake_retrieve)
    payload = direct_client.retrieve(request_payload).payload

    assert payload["retrieval_status"] == RetrievalStatus.SUCCEEDED.value
    assert payload["top_chunks"][0]["evidence_type"] == "ABSTRACT"
    assert payload["semantic_cache_match"] == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }
    assert "support_status" not in payload
