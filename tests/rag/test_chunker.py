"""
Unit tests for rag/ingestion/chunker.py (SCRUM-179).

Tests cover every individual function and the full orchestration pipeline,
including edge-cases like no-section fallback, short-paragraph merging,
SKIP_SECTIONS filtering, and oversized paragraphs being split correctly.
"""

import pytest

from rag.ingestion.chunker import (
    _is_heading,
    _looks_like_heading,
    _merge_short_paragraphs,
    chunk_text,
    count_tokens,
    normalize_section_name,
    should_skip_section,
    split_into_sections,
    SECTION_WEIGHTS,
    MIN_PARAGRAPH_TOKENS,
    TARGET_CHUNK_SIZE,
)
from rag.ingestion.models import (
    ChunkerInput,
    ChunkerOutput,
    EvidenceAvailability,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_input(
    text: str,
    availability: EvidenceAvailability = EvidenceAvailability.FULL_TEXT_AVAILABLE,
    doi: str = "10.0000/test.2024.001",
) -> ChunkerInput:
    """Build a minimal ChunkerInput for testing."""
    return ChunkerInput(
        clean_text=text,
        evidence_availability=availability,
        doi=doi,
    )


def long_text(token_target: int = TARGET_CHUNK_SIZE + 50) -> str:
    """Return a string whose token count reliably exceeds token_target."""
    # Build up the string incrementally until count_tokens confirms we're over.
    sentence = "The patient demonstrated significant cardiovascular improvement following the intervention. "
    result = ""
    while count_tokens(result) <= token_target:
        result += sentence
    return result.strip()


# ── count_tokens ──────────────────────────────────────────────────────────────


class TestCountTokens:
    def test_empty_string_is_zero(self):
        assert count_tokens("") == 0

    def test_single_word(self):
        # "hello" is 1 token in cl100k_base
        assert count_tokens("hello") == 1

    def test_sentence_has_positive_count(self):
        assert count_tokens("Exercise reduces heart disease risk by 35 percent.") > 5

    def test_longer_text_has_more_tokens(self):
        short = "hello"
        long = "hello world how are you doing today"
        assert count_tokens(long) > count_tokens(short)


# ── _looks_like_heading ───────────────────────────────────────────────────────


class TestLooksLikeHeading:
    def test_all_caps_word(self):
        assert _looks_like_heading("ABSTRACT") is True

    def test_all_caps_phrase(self):
        assert _looks_like_heading("INTRODUCTION AND OVERVIEW") is True

    def test_numbered_decimal(self):
        assert _looks_like_heading("1. Introduction") is True

    def test_numbered_subsection(self):
        assert _looks_like_heading("2.1 Data Collection") is True

    def test_roman_numeral(self):
        assert _looks_like_heading("III. Results") is True

    def test_title_case_short(self):
        assert _looks_like_heading("Related Work") is True

    def test_title_case_single_word(self):
        assert _looks_like_heading("Methods") is True

    def test_lowercase_sentence_rejected(self):
        assert _looks_like_heading("this is a normal sentence.") is False

    def test_ends_with_period_rejected(self):
        # A sentence ending with period should NOT be a heading.
        assert _looks_like_heading("Exercise reduces risk.") is False

    def test_empty_string_rejected(self):
        assert _looks_like_heading("") is False

    def test_long_phrase_rejected(self):
        # More than 8 words without a numbered prefix → not a heading
        assert _looks_like_heading("This Is A Very Long Title With Too Many Words Here") is False


# ── _is_heading (with context) ────────────────────────────────────────────────


class TestIsHeading:
    def test_heading_followed_by_blank_line(self):
        assert _is_heading("Introduction", "") is True

    def test_heading_followed_by_indented_line(self):
        assert _is_heading("Methods", "    This study used...") is True

    def test_heading_at_eof(self):
        assert _is_heading("Conclusion", None) is True

    def test_heading_followed_by_content_rejected(self):
        # If the next line is non-blank and non-indented, it's not a heading.
        assert _is_heading("Introduction", "This study investigates...") is False

    def test_too_long_line_rejected(self):
        long_line = "A" * 61
        assert _is_heading(long_line, "") is False

    def test_empty_line_rejected(self):
        assert _is_heading("", "") is False

    def test_numbered_heading_with_blank_after(self):
        assert _is_heading("2. Methods", "") is True

    def test_sentence_ending_period_rejected(self):
        assert _is_heading("Exercise reduces risk.", "") is False


# ── normalize_section_name ────────────────────────────────────────────────────


class TestNormalizeSectionName:
    def test_methodology_maps_to_methods(self):
        assert normalize_section_name("methodology") == "methods"

    def test_findings_maps_to_results(self):
        assert normalize_section_name("findings") == "results"

    def test_literature_review_maps_to_related_work(self):
        assert normalize_section_name("literature review") == "related_work"

    def test_conclusions_maps_to_conclusion(self):
        assert normalize_section_name("conclusions") == "conclusion"

    def test_strips_number_prefix(self):
        assert normalize_section_name("2. Methodology") == "methods"

    def test_strips_roman_numeral_prefix(self):
        assert normalize_section_name("III. Results") == "results"

    def test_strips_subsection_prefix(self):
        assert normalize_section_name("2.1 Experimental Setup") == "methods"

    def test_unknown_section_returned_lowercased(self):
        result = normalize_section_name("Future Work")
        assert result == "future work"

    def test_strips_trailing_colon(self):
        assert normalize_section_name("Methods:") == "methods"

    def test_case_insensitive(self):
        assert normalize_section_name("METHODOLOGY") == "methods"

    def test_direct_match_methods(self):
        assert normalize_section_name("methods") == "methods"

    def test_direct_match_results(self):
        assert normalize_section_name("results") == "results"


# ── should_skip_section ───────────────────────────────────────────────────────


class TestShouldSkipSection:
    def test_references_skipped(self):
        assert should_skip_section("references") is True

    def test_bibliography_skipped(self):
        assert should_skip_section("bibliography") is True

    def test_acknowledgements_skipped(self):
        assert should_skip_section("acknowledgements") is True

    def test_funding_skipped(self):
        assert should_skip_section("funding") is True

    def test_appendix_skipped(self):
        assert should_skip_section("appendix") is True

    def test_results_not_skipped(self):
        assert should_skip_section("results") is False

    def test_methods_not_skipped(self):
        assert should_skip_section("methods") is False

    def test_unknown_not_skipped(self):
        assert should_skip_section("unknown") is False


# ── split_into_sections ───────────────────────────────────────────────────────


class TestSplitIntoSections:
    def test_detects_two_sections(self):
        text = (
            "Introduction\n"
            "\n"
            "This study investigates exercise.\n"
            "\n"
            "Methods\n"
            "\n"
            "We collected data from 100 participants.\n"
        )
        sections = split_into_sections(text)
        names = [s[0] for s in sections]
        assert "introduction" in names
        assert "methods" in names

    def test_content_assigned_to_correct_section(self):
        text = (
            "Results\n"
            "\n"
            "Participants showed a 28% reduction.\n"
        )
        sections = split_into_sections(text)
        assert sections[0][0] == "results"
        assert "28% reduction" in sections[0][1]

    def test_skip_section_excluded(self):
        text = (
            "Introduction\n"
            "\n"
            "Body text here.\n"
            "\n"
            "References\n"
            "\n"
            "[1] Smith 2020\n"
        )
        sections = split_into_sections(text)
        names = [s[0] for s in sections]
        assert "references" not in names

    def test_no_headings_returns_empty_list(self):
        text = "Plain text with no headings whatsoever. Just content."
        sections = split_into_sections(text)
        # Returns empty list so chunk_text knows to apply the fallback path.
        assert sections == []

    def test_content_before_first_heading_is_unknown(self):
        text = (
            "Preamble text with no heading.\n"
            "\n"
            "Introduction\n"
            "\n"
            "Actual intro text.\n"
        )
        sections = split_into_sections(text)
        names = [s[0] for s in sections]
        assert "unknown" in names

    def test_normalises_section_names(self):
        text = (
            "Methodology\n"
            "\n"
            "We used regression analysis.\n"
        )
        sections = split_into_sections(text)
        assert sections[0][0] == "methods"

    def test_numbered_headings_detected(self):
        text = (
            "1. Introduction\n"
            "\n"
            "Some intro text.\n"
            "\n"
            "2. Methods\n"
            "\n"
            "Some methods text.\n"
        )
        sections = split_into_sections(text)
        names = [s[0] for s in sections]
        assert "introduction" in names
        assert "methods" in names

    def test_empty_sections_omitted(self):
        """A heading with no following content should produce no entry."""
        text = (
            "Introduction\n"
            "\n"
            "Methods\n"
            "\n"
            "We collected data.\n"
        )
        sections = split_into_sections(text)
        # "Introduction" has no content (Methods heading follows immediately)
        names = [s[0] for s in sections]
        assert "introduction" not in names
        assert "methods" in names


# ── _merge_short_paragraphs ───────────────────────────────────────────────────


class TestMergeShortParagraphs:
    def test_short_paragraph_merged_with_next(self):
        short = "Short."  # well under 50 tokens
        normal = "This paragraph has enough content to stand on its own as a unit of text."
        merged = _merge_short_paragraphs([short, normal])
        assert len(merged) == 1
        assert short in merged[0]
        assert normal in merged[0]

    def test_long_paragraphs_kept_separate(self):
        # Build two paragraphs each with > 50 tokens.
        para = ("cardiovascular disease risk factors include hypertension diabetes "
                "and obesity according to multiple clinical studies. " * 5)
        merged = _merge_short_paragraphs([para, para])
        assert len(merged) == 2

    def test_empty_list_returns_empty(self):
        assert _merge_short_paragraphs([]) == []

    def test_single_paragraph_unchanged(self):
        para = "Only one paragraph."
        result = _merge_short_paragraphs([para])
        assert result == [para]

    def test_multiple_short_paragraphs_all_merged(self):
        shorts = ["One.", "Two.", "Three.", "Four."]
        merged = _merge_short_paragraphs(shorts)
        # All four are too short individually, so they collapse into one.
        assert len(merged) == 1


# ── chunk_text (orchestrator) ─────────────────────────────────────────────────


class TestChunkText:
    def test_returns_chunker_output_type(self):
        result = chunk_text(make_input("Simple text with no sections."))
        assert isinstance(result, ChunkerOutput)

    def test_doi_passed_through(self):
        result = chunk_text(make_input("Text.", doi="10.9999/example"))
        assert result.doi == "10.9999/example"

    def test_total_chunks_matches_list_length(self):
        result = chunk_text(make_input("Some content without sections."))
        assert result.total_chunks == len(result.chunks)

    def test_fallback_used_when_no_sections(self):
        result = chunk_text(make_input("Plain text with no section headings at all."))
        assert result.fallback_used is True

    def test_fallback_not_used_when_sections_found(self):
        text = "Introduction\n\nSome intro content here.\n\nMethods\n\nWe did things."
        result = chunk_text(make_input(text))
        assert result.fallback_used is False

    def test_chunk_metadata_fields_populated(self):
        text = "Results\n\nParticipants showed a 28% reduction in risk."
        result = chunk_text(make_input(text, doi="10.1234/test"))
        assert result.chunks
        chunk = result.chunks[0]
        assert chunk.section == "results"
        assert chunk.priority == SECTION_WEIGHTS["results"]
        assert chunk.paper_doi == "10.1234/test"
        assert chunk.evidence_type == "FULL_TEXT"
        assert chunk.token_count > 0

    def test_chunk_id_format(self):
        result = chunk_text(make_input("Results\n\nSome findings.", doi="10.1234/test"))
        chunk = result.chunks[0]
        # chunk_id must start with a doi-derived slug and contain "_chunk_"
        assert "_chunk_" in chunk.id if hasattr(chunk, "id") else "_chunk_" in chunk.chunk_id

    def test_abstract_evidence_type(self):
        text = "Some abstract content about cardiovascular risk."
        result = chunk_text(make_input(text, availability=EvidenceAvailability.ABSTRACT_AVAILABLE))
        assert all(c.evidence_type == "ABSTRACT" for c in result.chunks)

    def test_full_text_evidence_type(self):
        text = "Introduction\n\nFull paper text with multiple sections."
        result = chunk_text(make_input(text, availability=EvidenceAvailability.FULL_TEXT_AVAILABLE))
        assert all(c.evidence_type == "FULL_TEXT" for c in result.chunks)

    def test_chunk_indices_are_sequential(self):
        text = (
            "Introduction\n\nIntro content here with several words.\n\n"
            "Methods\n\nMethods content here with several words.\n\n"
            "Results\n\nResults content with findings here.\n"
        )
        result = chunk_text(make_input(text))
        indices = [c.chunk_index for c in result.chunks]
        assert indices == list(range(len(indices)))

    def test_skip_section_produces_no_chunks(self):
        text = (
            "Introduction\n\nSome real content.\n\n"
            "References\n\n[1] Smith 2020. Some paper title."
        )
        result = chunk_text(make_input(text))
        sections = [c.section for c in result.chunks]
        assert "references" not in sections

    def test_long_section_split_into_multiple_chunks(self):
        """A section exceeding TARGET_CHUNK_SIZE tokens must produce multiple chunks."""
        body = long_text(TARGET_CHUNK_SIZE + 100)
        text = f"Results\n\n{body}"
        result = chunk_text(make_input(text))
        results_chunks = [c for c in result.chunks if c.section == "results"]
        assert len(results_chunks) > 1

    def test_all_chunks_within_token_limit(self):
        """No chunk should exceed TARGET_CHUNK_SIZE tokens."""
        body = long_text(TARGET_CHUNK_SIZE * 3)
        text = f"Methods\n\n{body}"
        result = chunk_text(make_input(text))
        for chunk in result.chunks:
            assert chunk.token_count <= TARGET_CHUNK_SIZE

    def test_sections_found_list_populated(self):
        text = (
            "Introduction\n\nIntro text here.\n\n"
            "Methods\n\nMethods text here.\n"
        )
        result = chunk_text(make_input(text))
        assert "introduction" in result.sections_found
        assert "methods" in result.sections_found

    def test_priority_weight_applied_correctly(self):
        text = "Results\n\nWe observed a significant effect in our experiment."
        result = chunk_text(make_input(text))
        for chunk in result.chunks:
            assert chunk.priority == SECTION_WEIGHTS["results"]  # 1.3

    def test_unknown_section_gets_default_priority(self):
        result = chunk_text(make_input("Plain text no sections."))
        for chunk in result.chunks:
            assert chunk.priority == SECTION_WEIGHTS["unknown"]  # 1.0
