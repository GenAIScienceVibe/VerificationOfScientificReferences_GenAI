"""
Unit tests for rag/evaluation/latency.py (SCRUM-185).

Testing strategy:
  - No API calls: all network-touching functions (_embed_single, _embed_batch,
    run_latency_profile) are excluded from the unit test suite.
  - We test: Pydantic models, _count_tokens, _compute_stats, _save_report,
    TEST_CHUNKS content, and constants — i.e. every piece of pure logic.
  - The integration path (run_latency_profile) is validated by running the
    script directly against the real API after unit tests pass.
"""

import json
from pathlib import Path

import pytest

from rag.evaluation.latency import (
    COST_PER_TOKEN_USD,
    DEFAULT_OUTPUT_PATH,
    EMBEDDING_MODEL,
    ESTIMATED_CHUNKS_PER_PAPER,
    TEST_CHUNKS,
    BatchCallResult,
    CallResult,
    LatencyReport,
    LatencyStats,
    _compute_stats,
    _count_tokens,
    _save_report,
)


# ── Constants ──────────────────────────────────────────────────────────────────


class TestConstants:
    def test_embedding_model_name(self):
        assert EMBEDDING_MODEL == "openai/text-embedding-3-small"

    def test_cost_per_token_is_correct(self):
        # $0.02 per 1M tokens → $0.00000002 per token
        assert abs(COST_PER_TOKEN_USD - 0.02 / 1_000_000) < 1e-15

    def test_estimated_chunks_per_paper_reasonable(self):
        # Should be between 50 and 200 — the value from CLAUDE.md context
        assert 50 <= ESTIMATED_CHUNKS_PER_PAPER <= 200

    def test_default_output_path(self):
        assert DEFAULT_OUTPUT_PATH.parts == ("data", "evaluation", "latency_results.json")


# ── TEST_CHUNKS ────────────────────────────────────────────────────────────────


class TestTestChunks:
    def test_exactly_10_chunks(self):
        assert len(TEST_CHUNKS) == 10

    def test_all_chunks_are_strings(self):
        for chunk in TEST_CHUNKS:
            assert isinstance(chunk, str)

    def test_no_empty_chunks(self):
        for chunk in TEST_CHUNKS:
            assert len(chunk.strip()) > 0

    def test_chunks_vary_in_length(self):
        lengths = [len(c) for c in TEST_CHUNKS]
        assert max(lengths) > min(lengths) * 2  # at least 2× variance

    def test_chunks_are_plausible_scientific_text(self):
        # Every chunk should contain at least one full word (not just symbols)
        for chunk in TEST_CHUNKS:
            words = [w for w in chunk.split() if w.isalpha()]
            assert len(words) >= 5, f"Chunk too short or non-textual: {chunk[:40]}"


# ── _count_tokens ──────────────────────────────────────────────────────────────


class TestCountTokens:
    def test_empty_string_returns_zero(self):
        assert _count_tokens("") == 0

    def test_single_word(self):
        # "hello" is one token in cl100k_base
        count = _count_tokens("hello")
        assert count == 1

    def test_longer_text_returns_positive(self):
        text = "Regular aerobic exercise reduces cardiovascular disease risk by 35 percent."
        assert _count_tokens(text) > 0

    def test_returns_int(self):
        assert isinstance(_count_tokens("test"), int)

    def test_longer_text_has_more_tokens(self):
        short = "Exercise helps."
        long = "Regular aerobic exercise has been shown to substantially reduce the risk of cardiovascular disease."
        assert _count_tokens(long) > _count_tokens(short)

    def test_all_test_chunks_have_nonzero_token_count(self):
        for chunk in TEST_CHUNKS:
            assert _count_tokens(chunk) > 0

    def test_token_counts_are_plausible(self):
        # Each synthetic chunk should have between 10 and 300 tokens
        for chunk in TEST_CHUNKS:
            count = _count_tokens(chunk)
            assert 10 <= count <= 300, (
                f"Unexpected token count {count} for chunk: {chunk[:60]}"
            )


# ── _compute_stats ─────────────────────────────────────────────────────────────


class TestComputeStats:
    def test_basic_uniform_latencies(self):
        latencies = [100.0, 100.0, 100.0, 100.0]
        stats = _compute_stats(latencies)
        assert stats.mean_ms == 100.0
        assert stats.median_ms == 100.0
        assert stats.min_ms == 100.0
        assert stats.max_ms == 100.0
        assert stats.stdev_ms == 0.0

    def test_mean_is_average(self):
        latencies = [100.0, 200.0, 300.0]
        stats = _compute_stats(latencies)
        assert abs(stats.mean_ms - 200.0) < 0.01

    def test_median_for_even_count(self):
        latencies = [10.0, 20.0, 30.0, 40.0]
        stats = _compute_stats(latencies)
        # median of [10, 20, 30, 40] = (20 + 30) / 2 = 25
        assert abs(stats.median_ms - 25.0) < 0.01

    def test_min_and_max(self):
        latencies = [50.0, 200.0, 100.0, 150.0, 75.0]
        stats = _compute_stats(latencies)
        assert stats.min_ms == 50.0
        assert stats.max_ms == 200.0

    def test_p95_within_range(self):
        latencies = list(range(1, 101))  # 1..100
        latencies = [float(x) for x in latencies]
        stats = _compute_stats(latencies)
        # p95 index = int(100 * 0.95) = 95 → value 96 (0-based, sorted)
        assert stats.p95_ms == 96.0

    def test_p95_single_element(self):
        stats = _compute_stats([42.0])
        assert stats.p95_ms == 42.0

    def test_returns_latency_stats_model(self):
        stats = _compute_stats([100.0, 200.0])
        assert isinstance(stats, LatencyStats)

    def test_stdev_nonzero_for_varying_latencies(self):
        latencies = [100.0, 200.0, 150.0, 180.0]
        stats = _compute_stats(latencies)
        assert stats.stdev_ms > 0.0

    def test_values_are_rounded_to_two_decimal_places(self):
        # 1/3 ms would be 0.333...
        latencies = [1.0 / 3.0, 2.0 / 3.0]
        stats = _compute_stats(latencies)
        # After rounding to 2 dp, the string representation should not be long
        assert len(str(stats.mean_ms).split(".")[-1]) <= 2

    def test_realistic_ten_call_latencies(self):
        # Representative latencies like we'd see from the API (200–900 ms)
        latencies = [350.0, 420.0, 290.0, 510.0, 380.0, 600.0, 270.0, 450.0, 320.0, 490.0]
        stats = _compute_stats(latencies)
        assert stats.min_ms <= stats.mean_ms <= stats.max_ms
        assert stats.p95_ms <= stats.max_ms


# ── Pydantic models ────────────────────────────────────────────────────────────


class TestCallResult:
    def test_valid_construction(self):
        result = CallResult(
            call_index=1,
            chunk_preview="Exercise reduces risk.",
            token_count=4,
            latency_ms=350.25,
            cost_usd=0.0000001,
        )
        assert result.call_index == 1
        assert result.token_count == 4

    def test_chunk_preview_stored_as_str(self):
        result = CallResult(
            call_index=1,
            chunk_preview="test",
            token_count=1,
            latency_ms=100.0,
            cost_usd=0.0,
        )
        assert isinstance(result.chunk_preview, str)

    def test_cost_can_be_very_small(self):
        result = CallResult(
            call_index=1,
            chunk_preview="x",
            token_count=1,
            latency_ms=100.0,
            cost_usd=COST_PER_TOKEN_USD,
        )
        assert result.cost_usd == COST_PER_TOKEN_USD


class TestBatchCallResult:
    def test_valid_construction(self):
        result = BatchCallResult(
            total_tokens=500,
            latency_ms=620.5,
            cost_usd=0.00001,
        )
        assert result.total_tokens == 500


class TestLatencyStats:
    def test_valid_construction(self):
        stats = LatencyStats(
            min_ms=200.0,
            max_ms=800.0,
            mean_ms=450.0,
            median_ms=430.0,
            p95_ms=750.0,
            stdev_ms=120.0,
        )
        assert stats.p95_ms == 750.0


class TestLatencyReport:
    def _make_report(self) -> LatencyReport:
        stats = LatencyStats(
            min_ms=200.0,
            max_ms=800.0,
            mean_ms=450.0,
            median_ms=430.0,
            p95_ms=750.0,
            stdev_ms=120.0,
        )
        batch = BatchCallResult(
            total_tokens=500,
            latency_ms=620.0,
            cost_usd=0.00001,
        )
        calls = [
            CallResult(
                call_index=i,
                chunk_preview=f"chunk {i}",
                token_count=50,
                latency_ms=float(200 + i * 50),
                cost_usd=50 * COST_PER_TOKEN_USD,
            )
            for i in range(1, 11)
        ]
        return LatencyReport(
            embedding_model=EMBEDDING_MODEL,
            timestamp="2026-06-15T12:00:00+00:00",
            num_individual_calls=10,
            total_tokens_individual=500,
            total_cost_individual_usd=500 * COST_PER_TOKEN_USD,
            avg_cost_per_call_usd=50 * COST_PER_TOKEN_USD,
            estimated_cost_per_paper_usd=ESTIMATED_CHUNKS_PER_PAPER * 50 * COST_PER_TOKEN_USD,
            latency_stats=stats,
            batch_comparison=batch,
            individual_calls=calls,
        )

    def test_valid_construction(self):
        report = self._make_report()
        assert report.num_individual_calls == 10

    def test_serialises_to_json(self):
        report = self._make_report()
        json_str = report.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["num_individual_calls"] == 10
        assert "latency_stats" in parsed
        assert "individual_calls" in parsed
        assert len(parsed["individual_calls"]) == 10

    def test_individual_calls_count_matches_field(self):
        report = self._make_report()
        assert len(report.individual_calls) == report.num_individual_calls


# ── _save_report ───────────────────────────────────────────────────────────────


class TestSaveReport:
    def _make_minimal_report(self) -> LatencyReport:
        stats = LatencyStats(
            min_ms=300.0,
            max_ms=600.0,
            mean_ms=450.0,
            median_ms=440.0,
            p95_ms=590.0,
            stdev_ms=80.0,
        )
        batch = BatchCallResult(
            total_tokens=400,
            latency_ms=500.0,
            cost_usd=400 * COST_PER_TOKEN_USD,
        )
        calls = [
            CallResult(
                call_index=i,
                chunk_preview=f"test chunk {i}",
                token_count=40,
                latency_ms=400.0 + i * 10,
                cost_usd=40 * COST_PER_TOKEN_USD,
            )
            for i in range(1, 11)
        ]
        return LatencyReport(
            embedding_model=EMBEDDING_MODEL,
            timestamp="2026-06-15T12:00:00+00:00",
            num_individual_calls=10,
            total_tokens_individual=400,
            total_cost_individual_usd=400 * COST_PER_TOKEN_USD,
            avg_cost_per_call_usd=40 * COST_PER_TOKEN_USD,
            estimated_cost_per_paper_usd=ESTIMATED_CHUNKS_PER_PAPER * 40 * COST_PER_TOKEN_USD,
            latency_stats=stats,
            batch_comparison=batch,
            individual_calls=calls,
        )

    def test_creates_file(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "nested" / "dir" / "latency_results.json"
        _save_report(report, out)
        assert out.exists()

    def test_file_is_valid_json(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        parsed = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_json_contains_required_keys(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        required = {
            "embedding_model",
            "timestamp",
            "num_individual_calls",
            "latency_stats",
            "batch_comparison",
            "individual_calls",
            "estimated_cost_per_paper_usd",
        }
        assert required.issubset(set(data.keys()))

    def test_returns_the_path(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        returned = _save_report(report, out)
        assert returned == out

    def test_default_path_used_when_none_passed(self, tmp_path, monkeypatch):
        # Redirect the default output path to a temp dir so we don't write to
        # data/ during the test run.
        import rag.evaluation.latency as latency_module
        new_default = tmp_path / "latency_results.json"
        monkeypatch.setattr(latency_module, "DEFAULT_OUTPUT_PATH", new_default)
        report = self._make_minimal_report()
        returned = _save_report(report, None)
        assert returned == new_default
        assert new_default.exists()

    def test_json_is_indented(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        raw = out.read_text(encoding="utf-8")
        # Indented JSON has newlines; compact JSON does not
        assert "\n" in raw

    def test_individual_calls_preserved_in_json(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["individual_calls"]) == 10

    def test_latency_stats_fields_preserved(self, tmp_path):
        report = self._make_minimal_report()
        out = tmp_path / "latency_results.json"
        _save_report(report, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        stats = data["latency_stats"]
        assert stats["min_ms"] == 300.0
        assert stats["max_ms"] == 600.0
        assert stats["mean_ms"] == 450.0
