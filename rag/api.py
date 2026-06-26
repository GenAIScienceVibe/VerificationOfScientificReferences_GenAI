"""
Integration handoff layer for the backend team (Jona and Sanilka).

This module is the single entry point the backend imports to call our RAG
sub-group's pipeline. We do NOT expose HTTP endpoints — the backend calls
these two plain Python functions directly from their FastAPI routes:

  - retrieve_evidence()  — Door 1: cleaner -> chunker -> embedder -> vector_store
  - verify_claim()       — Door 2: classifier -> verifier -> validator

Both functions take and return Pydantic models whose fields mirror the JSON
contracts documented in CLAUDE.md ("What we receive" / "What we return" for
each door) exactly, so the backend can serialise/deserialise them directly
at the FastAPI boundary.

Door 1 retrieval is hybrid: dense FAISS search (vector_store.py) and BM25
keyword search (bm25_retriever.py) each oversample candidates, which are
then merged via Reciprocal Rank Fusion and reranked by FlashRank
(hybrid_retriever.py). See retrieve_evidence()'s Step 5 for the wiring.
"""

import logging
from enum import Enum

from pydantic import BaseModel, Field

from rag.ingestion.chunker import chunk_text, count_tokens
from rag.ingestion.cleaner import clean_text
from rag.ingestion.models import (
    ChunkerInput,
    ChunkMetadata,
    CleanerInput,
    SourceEvidence,
)
from rag.prompts.classifier import classify_citation_type
from rag.prompts.config import LLM_TEMPERATURE
from rag.prompts.verifier import generate_verdict
from rag.retrieval.bm25_retriever import search as bm25_search
from rag.retrieval.embedder import embed_chunks
from rag.retrieval.hybrid_retriever import merge
from rag.retrieval.models import (
    Bm25RetrieverInput,
    EmbedderInput,
    EmbedderOutput,
    HybridRetrieverInput,
    VectorStoreInput,
)
from rag.retrieval.vector_store import SECTION_WEIGHTS, SIMILARITY_THRESHOLD, search
from rag.verification.models import Verdict, VerificationInput
from rag.verification.validator import validate_output

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Number of top chunks returned to the backend from Door 1.
DOOR1_TOP_K = 5

# Candidates each retriever (dense + BM25) fetches before RRF/FlashRank
# narrow the pool down to DOOR1_TOP_K, mirroring the oversample-then-rerank
# shape already used inside vector_store.py and hybrid_retriever.py.
RETRIEVAL_CANDIDATE_K = DOOR1_TOP_K * 3

# Dense fallback scores are cosine similarity (0-1) times a section weight
# that can exceed 1.0 (e.g. 1.3 for Results/Methods/Experiments). Dividing
# by the largest possible section weight normalizes those scores back to
# 0-1 without changing their relative order. FlashRank's rerank_score is
# already a 0-1 relevance probability and is never divided by this.
MAX_SECTION_WEIGHT = max(SECTION_WEIGHTS.values())

# Per-paper embedding cache for retrieve_evidence(). Key is reference_id (always
# unique per paper) so multiple claims citing the same paper reuse embeddings.
# Falls back to doi if reference_id is absent. In-memory only, never persisted.
_embedding_cache: dict[str, EmbedderOutput] = {}


# ── Shared request/response models ───────────────────────────────────────────


class DoiStatus(str, Enum):
    """DOI resolution status as reported by the backend's DOI checker."""

    VALID = "VALID"
    INVALID = "INVALID"
    UNRESOLVABLE = "UNRESOLVABLE"


# DOI statuses for which we must not run the pipeline at all (CLAUDE.md:
# "If DOI status is INVALID or UNRESOLVABLE -> skip pipeline").
UNUSABLE_DOI_STATUSES = (DoiStatus.INVALID, DoiStatus.UNRESOLVABLE)


# ── Door 1 models (retrieve_evidence) ────────────────────────────────────────


class RetrieveEvidenceRequest(BaseModel):
    """Exact input contract for Door 1 (CLAUDE.md: 'What we receive (Door 1)')."""

    claim_id: str = Field(..., description="Backend's unique ID for this claim")
    reference_id: str = Field(..., description="Backend's unique ID for this reference")
    claim_text: str = Field(..., description="The scientific claim text as written in the document")
    citation_text: str = Field(..., description="The raw in-text citation, e.g. '(Johnson et al., 2019)'")
    doi: str = Field(..., description="DOI of the cited source paper")
    doi_status: DoiStatus = Field(..., description="Whether the DOI resolves")
    source_evidence: SourceEvidence = Field(
        ..., description="Raw source text plus how much of the paper was available"
    )


class RetrievalStatus(str, Enum):
    """Whether Door 1 produced usable evidence chunks."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class TopChunkResult(BaseModel):
    """A single ranked chunk as returned to the backend (Door 1 output)."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_text: str = Field(..., description="The chunk's text content")
    similarity_score: float = Field(..., description="Section-weighted cosine similarity to the claim")
    evidence_type: str = Field(..., description="'FULL_TEXT' or 'ABSTRACT'")


class RetrieveEvidenceResponse(BaseModel):
    """Exact output contract for Door 1 (CLAUDE.md: 'What we return (Door 1)')."""

    claim_id: str = Field(..., description="Echoed back from the request")
    reference_id: str = Field(..., description="Echoed back from the request")
    retrieval_status: RetrievalStatus = Field(..., description="SUCCEEDED or FAILED")
    top_chunks: list[TopChunkResult] = Field(
        default_factory=list, description="Top DOOR1_TOP_K chunks ranked by weighted similarity"
    )
    overall_similarity_score: float = Field(
        default=0.0, description="Weighted similarity score of the single best-ranked chunk"
    )
    retrieval_confidence: float = Field(
        default=0.0, description="Average weighted similarity score across all returned chunks"
    )


# ── Door 2 models (verify_claim) ─────────────────────────────────────────────


class SourceMetadata(BaseModel):
    """Source paper metadata supplied for Door 2 (title + abstract only)."""

    title: str = Field(..., description="Title of the cited source paper")
    abstract: str = Field(..., description="Abstract of the cited source paper")


class RetrievedEvidenceItem(BaseModel):
    """One evidence chunk as the backend re-sends it for Door 2 verification."""

    chunk_id: str = Field(..., description="Unique chunk identifier, from Door 1's output")
    chunk_text: str = Field(..., description="The chunk's text content")
    similarity_score: float = Field(..., description="Similarity score, from Door 1's output")


class VerifyClaimRequest(BaseModel):
    """Exact input contract for Door 2 (CLAUDE.md: 'What we receive (Door 2)')."""

    claim_text: str = Field(..., description="The scientific claim text as written in the document")
    citation_text: str = Field(..., description="The raw in-text citation, e.g. '(Johnson et al., 2019)'")
    doi_status: DoiStatus = Field(..., description="Whether the DOI resolves")
    metadata: SourceMetadata = Field(..., description="Title and abstract of the cited source")
    retrieved_evidence: list[RetrievedEvidenceItem] = Field(
        ..., description="Top chunks selected by the backend after Door 1"
    )
    overall_similarity_score: float = Field(
        ..., description="Overall similarity score carried over from Door 1's output"
    )


class VerifyClaimResponse(BaseModel):
    """Exact output contract for Door 2 (CLAUDE.md: 'What we return (Door 2)')."""

    support_status: Verdict = Field(..., description="One of the five verdict labels")
    confidence: float = Field(..., ge=0.0, le=1.0, description="LLM's confidence in the verdict")
    explanation: str = Field(..., description="Chain-of-thought reasoning behind the verdict")
    evidence_used: list[str] = Field(default_factory=list, description="chunk_id values relied on")
    limitations: str | None = Field(default=None, description="Caveats about the evidence, if any")
    human_review_required: bool = Field(..., description="True when a human must review this verdict")


# ── Door 1 private helpers ───────────────────────────────────────────────────


def _embed_single_text(text: str, doi: str) -> list[float]:
    """
    Embed one string (the claim) with the same model used for source chunks.

    embed_chunks() only accepts a list of ChunkMetadata, so we wrap the claim
    text in a throwaway ChunkMetadata. Its metadata fields are never inspected
    downstream — only the resulting embedding vector is used — so reusing
    embed_chunks() here avoids a second, duplicate OpenAI-client/retry
    implementation just for single-string embedding.
    """
    placeholder_chunk = ChunkMetadata(
        chunk_id=f"{doi}_claim_query",
        section="claim",
        priority=1.0,
        chunk_index=0,
        paper_doi=doi,
        evidence_type="CLAIM",
        chunk_text=text,
        token_count=count_tokens(text),
    )
    embedded = embed_chunks(EmbedderInput(chunks=[placeholder_chunk], doi=doi))
    return embedded.embedded_chunks[0].embedding


def _failed_retrieval(request: RetrieveEvidenceRequest) -> RetrieveEvidenceResponse:
    """Build the FAILED response shared by every Door 1 early-exit path."""
    return RetrieveEvidenceResponse(
        claim_id=request.claim_id,
        reference_id=request.reference_id,
        retrieval_status=RetrievalStatus.FAILED,
    )


# ── Door 2 private helpers ───────────────────────────────────────────────────


def _insufficient_evidence(reason: str) -> VerifyClaimResponse:
    """Build the INSUFFICIENT_EVIDENCE response for the Door 2 DOI-status gate."""
    return VerifyClaimResponse(
        support_status=Verdict.INSUFFICIENT_EVIDENCE,
        confidence=0.0,
        explanation=reason,
        evidence_used=[],
        limitations="No DOI verification was possible.",
        human_review_required=True,
    )


def _needs_human_review(reason: str) -> VerifyClaimResponse:
    """Build a NEEDS_HUMAN_REVIEW response when the LLM call itself fails."""
    return VerifyClaimResponse(
        support_status=Verdict.NEEDS_HUMAN_REVIEW,
        confidence=0.0,
        explanation=reason,
        evidence_used=[],
        limitations=None,
        human_review_required=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────


def retrieve_evidence(request: RetrieveEvidenceRequest) -> RetrieveEvidenceResponse:
    """
    Door 1 — run the full retrieval pipeline for one claim/reference pair.

    Receives:
        request.claim_id:        backend's unique ID for this claim.
        request.reference_id:    backend's unique ID for this reference.
        request.claim_text:      the scientific claim as written in the document.
        request.citation_text:   the raw in-text citation (unused by retrieval
                                  itself — passed through for backend logging).
        request.doi:             DOI of the cited source paper.
        request.doi_status:      VALID / INVALID / UNRESOLVABLE.
        request.source_evidence: raw source text plus evidence_availability
                                  (FULL_TEXT_AVAILABLE / ABSTRACT_AVAILABLE /
                                  UNAVAILABLE) and the source URL.

    Pipeline (when doi_status is VALID):
        1. clean_text()   — strip noise and the references section.
        2. chunk_text()   — section-aware, token-bounded chunking.
        3. embed_chunks() — embed every source chunk, or reuse the cached
           EmbedderOutput from an earlier claim against the same DOI in this
           run (_embedding_cache, SCRUM-264).
        4. _embed_single_text() — embed the claim with the same model.
        5. Hybrid retrieval — dense search() and BM25 bm25_search() each
           oversample RETRIEVAL_CANDIDATE_K candidates, then merge()
           combines them via Reciprocal Rank Fusion and reranks the top
           pool with FlashRank, narrowing down to DOOR1_TOP_K chunks.

    Returns:
        RetrieveEvidenceResponse with:
          - retrieval_status: SUCCEEDED if at least one chunk was retrieved,
            FAILED otherwise.
          - top_chunks: up to DOOR1_TOP_K chunks, each with a similarity_score
            (FlashRank's relevance score when reranking succeeded, otherwise
            the chunk's dense cosine-weighted score divided by
            MAX_SECTION_WEIGHT as a fallback — both are normalized to the
            same 0-1 scale that Door 2's SIMILARITY_THRESHOLD expects).
          - overall_similarity_score: the best-ranked chunk's similarity_score.
          - retrieval_confidence: the average similarity_score across all
            returned chunks.

    Edge cases handled:
        - doi_status is INVALID or UNRESOLVABLE -> returns FAILED immediately,
          skips the pipeline entirely (no cleaning, chunking, or API calls).
        - Cleaning/chunking produces zero chunks (e.g. empty or all-skip-
          listed source text) -> returns FAILED.
        - Embedding, vector search, BM25 search, or merging raises any
          exception (e.g. missing OPENROUTER_API_KEY, a transient API error)
          -> logged and converted to FAILED rather than propagating to the
          backend. (FlashRank specifically never raises out of merge() — it
          falls back to RRF-only ordering internally; see hybrid_retriever.py.)
        - No chunks survive hybrid retrieval -> returns FAILED.
    """
    if request.doi_status in UNUSABLE_DOI_STATUSES:
        logger.warning(
            "claim_id=%s reference_id=%s — doi_status=%s, skipping retrieval pipeline.",
            request.claim_id, request.reference_id, request.doi_status.value,
        )
        return _failed_retrieval(request)

    try:
        # Step 1: strip noise (whitespace, page numbers, references section).
        cleaner_output = clean_text(
            CleanerInput(
                raw_text=request.source_evidence.text,
                evidence_availability=request.source_evidence.evidence_availability,
                doi=request.doi,
            )
        )

        # Step 2: section-aware, token-bounded chunking.
        chunker_output = chunk_text(
            ChunkerInput(
                clean_text=cleaner_output.clean_text,
                doi=request.doi,
                evidence_availability=request.source_evidence.evidence_availability,
            )
        )

        if not chunker_output.chunks:
            logger.warning(
                "claim_id=%s reference_id=%s — chunking produced zero chunks.",
                request.claim_id, request.reference_id,
            )
            return _failed_retrieval(request)

        # Step 3: embed every source chunk, reusing a cached embedding when
        # another claim earlier in this run already embedded the same paper.
        # Key by reference_id (always unique) rather than doi (empty when DOI
        # is missing, which would cause all DOI-less papers to collide in the
        # same cache slot and return wrong chunks — SCRUM-264).
        cache_key = request.reference_id or request.doi
        cached_embedder_output = _embedding_cache.get(cache_key)
        if cached_embedder_output is not None:
            embedder_output = cached_embedder_output
        else:
            embedder_output = embed_chunks(EmbedderInput(chunks=chunker_output.chunks, doi=request.doi))
            _embedding_cache[cache_key] = embedder_output

        # Step 4: embed the claim with the same embedding model.
        claim_embedding = _embed_single_text(request.claim_text, request.doi)

        # Step 5: hybrid retrieval — dense FAISS search and BM25 keyword
        # search each oversample candidates, then merge() combines them via
        # RRF and reranks the top pool with FlashRank.
        vector_output = search(
            VectorStoreInput(
                embedder_output=embedder_output,
                query_embedding=claim_embedding,
                top_k=RETRIEVAL_CANDIDATE_K,
            )
        )
        bm25_output = bm25_search(
            Bm25RetrieverInput(
                chunks=chunker_output.chunks,
                query=request.claim_text,
                top_k=RETRIEVAL_CANDIDATE_K,
            )
        )
        hybrid_output = merge(
            HybridRetrieverInput(
                dense_results=vector_output,
                bm25_results=bm25_output,
                claim=request.claim_text,
                top_k=DOOR1_TOP_K,
            )
        )

    except Exception as exc:
        logger.error(
            "claim_id=%s reference_id=%s — retrieval pipeline failed: %s",
            request.claim_id, request.reference_id, exc,
        )
        return _failed_retrieval(request)

    if not hybrid_output.top_chunks:
        logger.warning(
            "claim_id=%s reference_id=%s — hybrid retrieval returned zero chunks.",
            request.claim_id, request.reference_id,
        )
        return _failed_retrieval(request)

    # similarity_score prefers FlashRank's relevance score (0-1, same scale
    # Door 2's SIMILARITY_THRESHOLD expects); falls back to the chunk's dense
    # cosine-weighted score, normalized to 0-1 by MAX_SECTION_WEIGHT, on the
    # rare path where reranking itself failed.
    dense_weighted_by_id = {rc.chunk.chunk_id: rc.weighted_score for rc in vector_output.top_chunks}

    def _similarity_score(hc) -> float:
        if hc.rerank_score is not None:
            return hc.rerank_score
        return dense_weighted_by_id.get(hc.chunk.chunk_id, 0.0) / MAX_SECTION_WEIGHT

    top_chunks = [
        TopChunkResult(
            chunk_id=hc.chunk.chunk_id,
            chunk_text=hc.chunk.chunk_text,
            similarity_score=_similarity_score(hc),
            evidence_type=hc.chunk.evidence_type,
        )
        for hc in hybrid_output.top_chunks
    ]
    similarity_scores = [_similarity_score(hc) for hc in hybrid_output.top_chunks]

    return RetrieveEvidenceResponse(
        claim_id=request.claim_id,
        reference_id=request.reference_id,
        retrieval_status=RetrievalStatus.SUCCEEDED,
        top_chunks=top_chunks,
        overall_similarity_score=similarity_scores[0],
        retrieval_confidence=round(sum(similarity_scores) / len(similarity_scores), 6),
    )


def verify_claim(request: VerifyClaimRequest) -> VerifyClaimResponse:
    """
    Door 2 — run the full LLM verification pipeline for one claim.

    Receives:
        request.claim_text:             the scientific claim as written in
                                         the document.
        request.citation_text:          the raw in-text citation (unused by
                                         verification itself — passed through
                                         for backend logging).
        request.doi_status:             VALID / INVALID / UNRESOLVABLE.
        request.metadata:                title + abstract of the cited source.
        request.retrieved_evidence:     chunks selected by the backend after
                                         Door 1 (chunk_id, chunk_text,
                                         similarity_score only — no section
                                         label, since that is not part of
                                         this contract).
        request.overall_similarity_score: Door 1's overall similarity score,
                                         used here to derive the low_confidence
                                         signal for the human-review rule.

    Pipeline (when doi_status is VALID):
        1. classify_citation_type() — one LLM call to label the claim.
        2. Adapt request.retrieved_evidence into ChunkMetadata objects (the
           Door 2 contract does not carry section/priority/DOI metadata, so
           those fields are filled with neutral defaults — they only affect
           the rendered prompt's "(section: ...)" annotation, not the verdict
           logic).
        3. generate_verdict() — render verify.j2 and call Llama 4 Scout at
           temperature=LLM_TEMPERATURE.
        4. validate_output() — parse + validate the raw JSON, injecting
           human_review_required (confidence < 0.5, verdict ==
           PARTIALLY_SUPPORTED, or low similarity, per CLAUDE.md).

    Returns:
        VerifyClaimResponse with support_status, confidence, explanation,
        evidence_used, limitations, and human_review_required.

    Edge cases handled:
        - doi_status is INVALID or UNRESOLVABLE -> returns INSUFFICIENT_EVIDENCE
          immediately, skips the pipeline entirely, and always sets
          human_review_required=True (an unverifiable DOI must always be
          reviewed by a human, per backend safety policy).
        - The LLM call itself fails (missing OPENROUTER_API_KEY, network/API
          error) -> caught and converted to NEEDS_HUMAN_REVIEW.
        - The LLM's raw response fails Pydantic validation (malformed JSON,
          missing fields, bad verdict label) -> validate_output() already
          guarantees a NEEDS_HUMAN_REVIEW fallback; no extra handling needed.
    """
    logger.debug("verify_claim invoked (LLM_TEMPERATURE=%s)", LLM_TEMPERATURE)

    if request.doi_status in UNUSABLE_DOI_STATUSES:
        return _insufficient_evidence(
            f"DOI status is {request.doi_status.value} — skipping verification."
        )

    # Step 1: classify the citation type to give the LLM the right context.
    citation_type = classify_citation_type(request.claim_text)

    # Step 2: adapt the loose Door 2 evidence contract into ChunkMetadata.
    # section/priority/paper_doi/evidence_type are not part of this contract,
    # so neutral placeholders are used — they do not affect the verdict, only
    # the prompt's section annotation.
    chunks = [
        ChunkMetadata(
            chunk_id=item.chunk_id,
            section="unknown",
            priority=1.0,
            chunk_index=index,
            paper_doi="",
            evidence_type="UNKNOWN",
            chunk_text=item.chunk_text,
            token_count=count_tokens(item.chunk_text),
        )
        for index, item in enumerate(request.retrieved_evidence)
    ]

    verification_input = VerificationInput(
        claim_text=request.claim_text,
        citation_type=citation_type.value,
        chunks=chunks,
        doi="",  # not part of the Door 2 contract; only used for prompt context
    )

    # Step 3: render the prompt and call the LLM.
    try:
        raw_response = generate_verdict(verification_input)
    except Exception as exc:
        logger.error("LLM verification call failed: %s", exc)
        return _needs_human_review(f"LLM verification call failed: {exc}")

    # Step 4: low_confidence bridge — Door 2 gives us a similarity score, not
    # a boolean, so the same threshold vector_store.py uses internally is
    # reapplied here to decide whether to flag the verdict for human review.
    low_confidence = request.overall_similarity_score < SIMILARITY_THRESHOLD

    # Step 5: validate + fallback (never raises).
    output = validate_output(raw_response, low_confidence=low_confidence)

    return VerifyClaimResponse(
        support_status=output.verdict,
        confidence=output.confidence,
        explanation=output.explanation,
        evidence_used=output.evidence_used,
        limitations=output.limitations,
        human_review_required=output.human_review_required,
    )
