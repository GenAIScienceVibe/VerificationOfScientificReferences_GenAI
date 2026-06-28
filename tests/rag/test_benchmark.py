"""
Unit tests for rag/evaluation/benchmark.py (SCRUM-184).

Testing strategy:
  - No API calls: we test only the pure-logic helpers (_check_hit, _save_report,
    Pydantic model validation) so tests run instantly without a live key.
  - The integration path (run_benchmark) is validated by running the script
    directly against the real API after the unit tests pass.
  - RetrievedChunk objects are built with real ChunkMetadata so we are testing
    the actual data shapes that flow through the pipeline, not toy stand-ins.
"""

import json
import re

import pytest

from rag.ingestion.models import ChunkMetadata
from rag.retrieval.models import EmbeddedChunk, RetrievedChunk
from rag.evaluation.benchmark import (
    BENCHMARK_CASES,
    DEFAULT_OUTPUT_PATH,
    TOP_K,
    BenchmarkCase,
    BenchmarkReport,
    CaseResult,
    TopChunkPreview,
    _check_hit,
    _save_report,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_retrieved_chunk(
    rank: int,
    text: str,
    section: str = "results",
    weighted_score: float = 0.9,
) -> RetrievedChunk:
    """Build a minimal RetrievedChunk for testing _check_hit."""
    chunk = ChunkMetadata(
        chunk_id=f"test_chunk_{rank:03d}",
        section=section,
        priority=1.3,
        chunk_index=rank - 1,
        paper_doi="10.0000/test",
        evidence_type="FULL_TEXT",
        chunk_text=text,
        token_count=len(text.split()),
    )
    return RetrievedChunk(
        chunk=chunk,
        raw_score=0.8,
        weighted_score=weighted_score,
        rank=rank,
    )


def make_minimal_report(n_cases: int = 3, n_hits: int = 2) -> BenchmarkReport:
    """Build a BenchmarkReport for testing _save_report."""
    results = [
        CaseResult(
            case_id=f"case_{i:03d}",
            claim=f"Test claim {i}.",
            hit=(i < n_hits),
            rank_if_found=(1 if i < n_hits else None),
            top_chunks=[],
            total_chunks_indexed=5,
        )
        for i in range(n_cases)
    ]
    return BenchmarkReport(
        total_cases=n_cases,
        total_hits=n_hits,
        total_errors=0,
        accuracy_pct=round(n_hits / n_cases * 100, 1),
        top_k=TOP_K,
        embedding_model="openai/text-embedding-3-small",
        timestamp="2026-06-15T00:00:00+00:00",
        results=results,
    )


# ── _check_hit ─────────────────────────────────────────────────────────────────


class TestCheckHit:
    def test_hit_when_evidence_in_rank_1_chunk(self):
        chunks = [
            make_retrieved_chunk(1, "participants showed a 35 percent reduction in risk"),
            make_retrieved_chunk(2, "unrelated sentence about methodology"),
        ]
        hit, rank = _check_hit(chunks, "35 percent reduction in risk")
        assert hit is True
        assert rank == 1

    def test_hit_when_evidence_in_rank_3_chunk(self):
        """Evidence in rank 3 still counts as a hit@3."""
        chunks = [
            make_retrieved_chunk(1, "background information about the study"),
            make_retrieved_chunk(2, "description of the methods used"),
            make_retrieved_chunk(3, "participants showed a 35 percent reduction in risk"),
        ]
        hit, rank = _check_hit(chunks, "35 percent reduction in risk")
        assert hit is True
        assert rank == 3

    def test_miss_when_evidence_not_in_any_chunk(self):
        chunks = [
            make_retrieved_chunk(1, "background information about the study"),
            make_retrieved_chunk(2, "description of the methods used"),
            make_retrieved_chunk(3, "conclusions about future research"),
        ]
        hit, rank = _check_hit(chunks, "35 percent reduction in risk")
        assert hit is False
        assert rank is None

    def test_check_is_case_insensitive(self):
        chunks = [
            make_retrieved_chunk(1, "PARTICIPANTS SHOWED A 35 PERCENT REDUCTION IN RISK"),
        ]
        hit, rank = _check_hit(chunks, "35 percent reduction in risk")
        assert hit is True
        assert rank == 1

    def test_hit_on_partial_phrase_match(self):
        """A longer chunk that contains the evidence phrase counts as a hit."""
        long_text = (
            "After 24 months of follow-up, participants who performed regular "
            "aerobic exercise showed a 35 percent reduction in cardiovascular "
            "disease risk, with improvements across all secondary endpoints."
        )
        chunks = [make_retrieved_chunk(1, long_text)]
        hit, rank = _check_hit(
            chunks,
            "showed a 35 percent reduction in cardiovascular disease risk",
        )
        assert hit is True

    def test_hit_when_chunk_has_newline_inside_evidence_phrase(self):
        """Source texts are line-wrapped, so chunks often contain newlines inside
        what should match the evidence phrase. _check_hit must normalise whitespace
        so 'showed a\\n35 percent' matches 'showed a 35 percent'."""
        chunk_text = (
            "After 24 months, participants who performed regular aerobic exercise "
            "showed a\n35 percent reduction in cardiovascular disease risk."
        )
        chunks = [make_retrieved_chunk(1, chunk_text)]
        hit, rank = _check_hit(
            chunks,
            "showed a 35 percent reduction in cardiovascular disease risk",
        )
        assert hit is True
        assert rank == 1

    def test_empty_chunk_list_returns_miss(self):
        hit, rank = _check_hit([], "some evidence")
        assert hit is False
        assert rank is None

    def test_returns_rank_of_first_matching_chunk(self):
        """If evidence appears in multiple chunks, the lowest rank is returned."""
        evidence = "key finding about treatment"
        chunks = [
            make_retrieved_chunk(1, "unrelated content about background"),
            make_retrieved_chunk(2, f"results section: {evidence} was observed"),
            make_retrieved_chunk(3, f"discussion confirms {evidence}"),
        ]
        hit, rank = _check_hit(chunks, evidence)
        assert hit is True
        assert rank == 2  # first match wins


# ── _save_report ───────────────────────────────────────────────────────────────


class TestSaveReport:
    def test_creates_file_at_specified_path(self, tmp_path):
        report = make_minimal_report()
        output = tmp_path / "results" / "benchmark.json"

        returned_path = _save_report(report, output_path=output)

        assert returned_path == output
        assert output.exists()

    def test_creates_parent_directory_if_missing(self, tmp_path):
        report = make_minimal_report()
        deep_path = tmp_path / "a" / "b" / "c" / "results.json"

        _save_report(report, output_path=deep_path)

        assert deep_path.exists()

    def test_output_is_valid_json(self, tmp_path):
        report = make_minimal_report()
        output = tmp_path / "out.json"

        _save_report(report, output_path=output)

        content = output.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    def test_json_contains_expected_fields(self, tmp_path):
        report = make_minimal_report(n_cases=3, n_hits=2)
        output = tmp_path / "out.json"

        _save_report(report, output_path=output)

        parsed = json.loads(output.read_text(encoding="utf-8"))
        assert parsed["total_cases"] == 3
        assert parsed["total_hits"] == 2
        assert "accuracy_pct" in parsed
        assert "results" in parsed
        assert isinstance(parsed["results"], list)

    def test_returns_path_object(self, tmp_path):
        report = make_minimal_report()
        output = tmp_path / "out.json"
        result = _save_report(report, output_path=output)
        assert isinstance(result, type(output))


# ── BenchmarkReport model ──────────────────────────────────────────────────────


class TestBenchmarkReport:
    def test_accuracy_pct_is_correct(self):
        report = make_minimal_report(n_cases=5, n_hits=4)
        assert report.accuracy_pct == 80.0

    def test_zero_hits_gives_zero_accuracy(self):
        report = make_minimal_report(n_cases=3, n_hits=0)
        assert report.accuracy_pct == 0.0

    def test_all_hits_gives_100_accuracy(self):
        report = make_minimal_report(n_cases=5, n_hits=5)
        assert report.accuracy_pct == 100.0

    def test_results_list_length_matches_total_cases(self):
        report = make_minimal_report(n_cases=5, n_hits=3)
        assert len(report.results) == report.total_cases


# ── BenchmarkCase data ─────────────────────────────────────────────────────────


class TestBenchmarkCases:
    def test_five_cases_defined(self):
        assert len(BENCHMARK_CASES) == 5

    def test_all_case_ids_are_unique(self):
        ids = [c.case_id for c in BENCHMARK_CASES]
        assert len(ids) == len(set(ids))

    def test_expected_evidence_appears_in_source_text(self):
        """Every expected_evidence phrase must appear in the source text after
        whitespace normalisation.

        Source texts are line-wrapped, so the evidence phrase may span two lines.
        We normalise whitespace here the same way _check_hit does, so the test
        matches the actual runtime matching behaviour.
        """
        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", s).lower().strip()

        for case in BENCHMARK_CASES:
            assert norm(case.expected_evidence) in norm(case.source_text), (
                f"Case {case.case_id}: expected_evidence not found in source_text "
                f"(after whitespace normalisation).\n"
                f"Evidence: {case.expected_evidence!r}"
            )

    def test_all_cases_have_non_empty_claims(self):
        for case in BENCHMARK_CASES:
            assert case.claim.strip(), f"Case {case.case_id} has an empty claim"

    def test_all_cases_have_multi_section_source_text(self):
        """Each paper should have at least 3 section headings for realistic chunking."""
        for case in BENCHMARK_CASES:
            upper_lines = [
                line for line in case.source_text.splitlines()
                if line.strip().isupper() and len(line.strip()) > 2
            ]
            assert len(upper_lines) >= 3, (
                f"Case {case.case_id} has fewer than 3 detectable headings: "
                f"{upper_lines}"
            )
