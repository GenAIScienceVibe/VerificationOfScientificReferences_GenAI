from __future__ import annotations

from typing import Any

import pytest

from app.models.enums import DoiStatus, RetrievalStatus
from app.services.genai_verification import RealGenAiVerificationClient
from app.services.rag_ml_integration import (
    MockRagClient,
    RagDirectClient,
    RagResponseValidator,
    _DOI_STATUS_TO_RAG,
    _clamp_top_k,
)


DOI_STATUS_CASES = [
    pytest.param(DoiStatus.VALID.value, "VALID", id="valid"),
    pytest.param(DoiStatus.FOUND.value, "UNRESOLVABLE", id="found"),
    pytest.param(DoiStatus.MISSING.value, "UNRESOLVABLE", id="missing"),
    pytest.param(DoiStatus.LOOKUP_FAILED.value, "UNRESOLVABLE", id="lookup-failed"),
    pytest.param(DoiStatus.MALFORMED.value, "INVALID", id="malformed"),
    pytest.param(DoiStatus.INVALID.value, "INVALID", id="invalid"),
]

SAFE_FAILURE_MESSAGE = "RAG retrieval did not return usable evidence."
UNSAFE_RAG_ERROR_MESSAGES = [
    pytest.param(
        "Traceback: File /home/user/private/service.py line 42",
        id="raw-traceback",
    ),
    pytest.param(
        "upstream token=dummy-private-value",
        id="generic-token",
    ),
    pytest.param("/home/user/private/service.py", id="linux-path"),
    pytest.param("/Users/alice/project/private.py", id="macos-path"),
    pytest.param(r"C:\Users\alice\project\private.py", id="windows-path"),
    pytest.param("file:///home/user/private/source.pdf", id="file-url"),
    pytest.param("Authorization: Bearer abc123", id="authorization-bearer"),
    pytest.param("access_token=abc123", id="access-token"),
    pytest.param("refresh_token=abc123", id="refresh-token"),
    pytest.param("api_key=abc123", id="api-key"),
    pytest.param("password=abc123", id="password"),
    pytest.param("secret=abc123", id="secret"),
    pytest.param("sk-test-secret-value", id="sk-key"),
    pytest.param(
        "Traceback...\nFile /home/user/private/service.py line 42\nRuntimeError: failure",
        id="multiline-stack",
    ),
]


@pytest.mark.parametrize(("backend_status", "rag_status"), DOI_STATUS_CASES)
def test_door1_maps_every_backend_doi_status_safely(
    backend_status: str,
    rag_status: str,
) -> None:
    assert _DOI_STATUS_TO_RAG[backend_status] == rag_status
    assert (_DOI_STATUS_TO_RAG[backend_status] == "VALID") is (
        backend_status == DoiStatus.VALID.value
    )


@pytest.mark.parametrize(("backend_status", "rag_status"), DOI_STATUS_CASES)
def test_door2_maps_every_backend_doi_status_safely(
    backend_status: str,
    rag_status: str,
) -> None:
    assert RealGenAiVerificationClient._DOI_MAP[backend_status] == rag_status
    assert (RealGenAiVerificationClient._DOI_MAP[backend_status] == "VALID") is (
        backend_status == DoiStatus.VALID.value
    )


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        pytest.param(None, 5, 5, id="omitted"),
        pytest.param(0, 5, 1, id="below-minimum"),
        pytest.param(-4, 5, 1, id="negative"),
        pytest.param(3, 5, 3, id="requested-three"),
        pytest.param(99, 5, 20, id="above-maximum"),
        pytest.param("invalid", 5, 5, id="non-numeric"),
    ],
)
def test_top_k_is_bounded_safely(value: Any, default: int, expected: int) -> None:
    assert _clamp_top_k(value, default) == expected


def _direct_request(*, top_k: Any = None, source_url: str = "https://doi.org/10.1234/demo") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claim_id": "claim_1",
        "reference_id": "ref_1",
        "claim_text": "A scientific claim.",
        "citation_text": "(Smith, 2024)",
        "doi": "10.1234/demo",
        "doi_status": "VALID",
        "source_evidence": {
            "evidence_availability": "ABSTRACT_AVAILABLE",
            "text": "Source abstract text.",
            "source_url": source_url,
        },
    }
    if top_k is not None:
        payload["retrieval_options"] = {"top_k": top_k}
    return payload


@pytest.mark.parametrize(
    ("requested_top_k", "expected_top_k"),
    [
        pytest.param(1, 1, id="one"),
        pytest.param(3, 3, id="three"),
        pytest.param(None, 5, id="default"),
        pytest.param(100, 20, id="bounded-high"),
        pytest.param(0, 1, id="bounded-low"),
    ],
)
def test_real_adapter_passes_bounded_top_k_and_limits_chunks(
    monkeypatch: pytest.MonkeyPatch,
    requested_top_k: int | None,
    expected_top_k: int,
) -> None:
    direct = RagDirectClient()
    import rag.api as rag_api

    captured: dict[str, Any] = {}

    def fake_retrieve(request):
        captured["top_k"] = request.top_k
        chunks = [
            rag_api.TopChunkResult(
                chunk_id=f"chunk_{index}",
                chunk_text=f"Evidence chunk {index}",
                similarity_score=0.9 - index * 0.01,
                evidence_type="ABSTRACT",
            )
            for index in range(25)
        ]
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.SUCCEEDED,
            top_chunks=chunks,
            overall_similarity_score=0.9,
            retrieval_confidence=0.8,
        )

    monkeypatch.setattr(rag_api, "retrieve_evidence", fake_retrieve)

    result = direct.retrieve(_direct_request(top_k=requested_top_k))

    assert captured["top_k"] == expected_top_k
    assert len(result.payload["top_chunks"]) == expected_top_k
    assert result.payload["semantic_cache_match"] == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }


def test_mock_and_real_clients_share_bounded_top_k_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct = RagDirectClient()
    import rag.api as rag_api

    captured: dict[str, Any] = {}

    def fake_retrieve(request):
        captured["top_k"] = request.top_k
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.FAILED,
            error_message="No relevant evidence chunks were found.",
        )

    monkeypatch.setattr(rag_api, "retrieve_evidence", fake_retrieve)
    payload = _direct_request(top_k=0)

    real_result = direct.retrieve(payload)
    mock_result = MockRagClient().retrieve(payload)
    validated_real = RagResponseValidator().validate(
        real_result.payload,
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert captured["top_k"] == 1
    assert len(real_result.payload["top_chunks"]) <= 1
    assert len(mock_result.payload["top_chunks"]) <= 1
    assert validated_real["retrieval_status"] == RetrievalStatus.FAILED.value
    assert validated_real["error_message"] == "No relevant evidence chunks were found."


def test_real_adapter_adds_traceability_and_sanitizes_private_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct = RagDirectClient()
    import rag.api as rag_api

    def fake_retrieve(request):
        return rag_api.RetrieveEvidenceResponse(
            claim_id=request.claim_id,
            reference_id=request.reference_id,
            retrieval_status=rag_api.RetrievalStatus.SUCCEEDED,
            top_chunks=[
                rag_api.TopChunkResult(
                    chunk_id="chunk_1",
                    chunk_text="Traceable evidence.",
                    similarity_score=0.8,
                    evidence_type="ABSTRACT",
                )
            ],
            overall_similarity_score=0.8,
            retrieval_confidence=0.8,
        )

    monkeypatch.setattr(rag_api, "retrieve_evidence", fake_retrieve)

    public_payload = direct.retrieve(_direct_request()).payload
    validated_public = RagResponseValidator().validate(
        public_payload,
        claim_id="claim_1",
        reference_id="ref_1",
    )
    public = validated_public["top_chunks"][0]
    private = direct.retrieve(
        _direct_request(source_url="file:///home/user/private/source.pdf")
    ).payload["top_chunks"][0]
    loopback = direct.retrieve(
        _direct_request(source_url="http://127.0.0.1/private/source.pdf")
    ).payload["top_chunks"][0]

    assert public["source"] == "metadata_abstract"
    assert public["source_url"] == "https://doi.org/10.1234/demo"
    assert private["source"] == "metadata_abstract"
    assert private["source_url"] is None
    assert loopback["source_url"] is None
    assert "/home/user/private" not in str(private)


def test_validator_normalizes_scores_and_defaults_contract_fields() -> None:
    validated = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.SUCCEEDED.value,
            "top_chunks": [
                {
                    "chunk_id": "chunk_1",
                    "chunk_text": "Evidence",
                    "similarity_score": 1.4,
                    "evidence_type": "ABSTRACT",
                }
            ],
            "overall_similarity_score": -0.3,
            "retrieval_confidence": 1.2,
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert validated["top_chunks"][0]["similarity_score"] == 1.0
    assert validated["overall_similarity_score"] == 0.0
    assert validated["retrieval_confidence"] == 1.0
    assert validated["top_chunks"][0]["source"] == "unavailable"
    assert validated["top_chunks"][0]["source_url"] is None
    assert validated["semantic_cache_match"] == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }


def test_validator_rejects_non_finite_scores() -> None:
    with pytest.raises(ValueError, match="finite"):
        RagResponseValidator().validate(
            {
                "claim_id": "claim_1",
                "reference_id": "ref_1",
                "retrieval_status": RetrievalStatus.SUCCEEDED.value,
                "top_chunks": [
                    {
                        "chunk_text": "Evidence",
                        "similarity_score": float("nan"),
                    }
                ],
            },
            claim_id="claim_1",
            reference_id="ref_1",
        )


def test_failed_real_response_validates_with_safe_error_and_cache_default() -> None:
    validated = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.FAILED.value,
            "top_chunks": [],
            "overall_similarity_score": 0.0,
            "retrieval_confidence": 0.0,
            "error_message": "OPENROUTER_API_KEY=sk-secret-value",
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert validated["error_message"] == SAFE_FAILURE_MESSAGE
    assert "secret" not in validated["error_message"].casefold()
    assert validated["semantic_cache_match"] == {
        "matched": False,
        "cached_result_id": None,
        "similarity": None,
    }


@pytest.mark.parametrize("unsafe_message", UNSAFE_RAG_ERROR_MESSAGES)
def test_failed_response_sanitizes_unsafe_error_detail(
    unsafe_message: str,
) -> None:
    validated = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.FAILED.value,
            "top_chunks": [],
            "error_message": unsafe_message,
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert validated["error_message"] == SAFE_FAILURE_MESSAGE
    assert unsafe_message not in validated["error_message"]


@pytest.mark.parametrize(
    "safe_message",
    [
        "No relevant evidence chunks were found.",
        "Source evidence is unavailable or empty.",
        "Embedding service failed while preparing retrieval vectors.",
    ],
)
def test_failed_response_preserves_safe_error_detail(safe_message: str) -> None:
    validated = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.FAILED.value,
            "top_chunks": [],
            "error_message": safe_message,
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert validated["error_message"] == safe_message


def test_failed_response_normalizes_and_bounds_nonsensitive_error_detail() -> None:
    multiline = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.FAILED.value,
            "top_chunks": [],
            "error_message": "Temporary retrieval issue.\nRetry was exhausted.",
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )
    long_message = RagResponseValidator().validate(
        {
            "claim_id": "claim_1",
            "reference_id": "ref_1",
            "retrieval_status": RetrievalStatus.FAILED.value,
            "top_chunks": [],
            "error_message": "x" * 600,
        },
        claim_id="claim_1",
        reference_id="ref_1",
    )

    assert multiline["error_message"] == "Temporary retrieval issue. Retry was exhausted."
    assert long_message["error_message"] == "x" * 500
