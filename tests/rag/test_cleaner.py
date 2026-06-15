"""
Unit tests for rag/ingestion/cleaner.py (SCRUM-178).

Each test targets exactly one cleaning behaviour so failures are easy to
diagnose. We test both the private helpers directly and the public
`clean_text` orchestrator.
"""

import pytest

from rag.ingestion.cleaner import (
    _collapse_blank_lines,
    _normalize_whitespace,
    _remove_page_numbers,
    _remove_references_section,
    _remove_repeated_lines,
    clean_text,
)
from rag.ingestion.models import CleanerInput, EvidenceAvailability


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_input(raw_text: str, availability: EvidenceAvailability = EvidenceAvailability.FULL_TEXT_AVAILABLE) -> CleanerInput:
    """Build a minimal CleanerInput for testing."""
    return CleanerInput(
        raw_text=raw_text,
        evidence_availability=availability,
        doi="10.0000/test.2024.001",
    )


# ── _normalize_whitespace ─────────────────────────────────────────────────────


class TestNormalizeWhitespace:
    def test_crlf_becomes_lf(self):
        assert _normalize_whitespace("line1\r\nline2") == "line1\nline2"

    def test_cr_only_becomes_lf(self):
        assert _normalize_whitespace("line1\rline2") == "line1\nline2"

    def test_tabs_become_spaces(self):
        assert _normalize_whitespace("word1\tword2") == "word1 word2"

    def test_multiple_spaces_collapsed(self):
        assert _normalize_whitespace("word1   word2") == "word1 word2"

    def test_newlines_not_collapsed(self):
        """Newlines between paragraphs must be preserved, only inline spaces collapse."""
        result = _normalize_whitespace("para1\n\npara2")
        assert result == "para1\n\npara2"


# ── _remove_page_numbers ──────────────────────────────────────────────────────


class TestRemovePageNumbers:
    def test_bare_number_line(self):
        text = "Some content\n42\nMore content"
        result = _remove_page_numbers(text)
        assert "42" not in result.split("\n")[1] or result.count("42") == 0

    def test_page_n_pattern(self):
        text = "Content\nPage 3\nMore content"
        result = _remove_page_numbers(text)
        assert "Page 3" not in result

    def test_page_n_of_m_pattern(self):
        text = "Content\nPage 3 of 12\nMore content"
        result = _remove_page_numbers(text)
        assert "Page 3 of 12" not in result

    def test_n_of_m_pattern(self):
        text = "Content\n3 of 12\nMore content"
        result = _remove_page_numbers(text)
        assert "3 of 12" not in result

    def test_dash_number_dash_pattern(self):
        text = "Content\n- 5 -\nMore content"
        result = _remove_page_numbers(text)
        assert "- 5 -" not in result

    def test_number_in_sentence_preserved(self):
        """A number embedded in a sentence must NOT be stripped."""
        text = "There were 42 participants in the study."
        result = _remove_page_numbers(text)
        assert "42" in result


# ── _remove_repeated_lines ────────────────────────────────────────────────────


class TestRemoveRepeatedLines:
    def test_removes_repeated_header(self):
        header = "Journal of Science, Vol. 10"
        # Header appears 4 times, content appears once
        text = f"{header}\nIntroduction\n{header}\nBody text here.\n{header}\nConclusion.\n{header}"
        result = _remove_repeated_lines(text, threshold=3)
        assert header not in result

    def test_preserves_non_repeated_lines(self):
        text = "Unique line one\nUnique line two\nUnique line three"
        result = _remove_repeated_lines(text, threshold=3)
        assert "Unique line one" in result
        assert "Unique line two" in result

    def test_threshold_respected(self):
        """Lines appearing fewer times than threshold must be kept."""
        line = "Semi-repeated line"
        text = f"{line}\nOther content\n{line}"  # appears only twice
        result = _remove_repeated_lines(text, threshold=3)
        assert line in result

    def test_empty_lines_not_counted(self):
        """Empty lines should not be treated as repeated headers."""
        text = "Para one\n\n\nPara two\n\n\nPara three"
        result = _remove_repeated_lines(text, threshold=3)
        assert "Para one" in result


# ── _remove_references_section ────────────────────────────────────────────────


class TestRemoveReferencesSection:
    def test_removes_references_heading(self):
        text = "Body text here.\n\nReferences\n\n[1] Smith et al. 2020"
        result = _remove_references_section(text)
        assert "References" not in result
        assert "[1] Smith et al. 2020" not in result
        assert "Body text here." in result

    def test_removes_bibliography_heading(self):
        text = "Body text.\n\nBibliography\n\n[1] Jones 2019"
        result = _remove_references_section(text)
        assert "Bibliography" not in result
        assert "Body text." in result

    def test_removes_works_cited_heading(self):
        text = "Body text.\n\nWorks Cited\n\nSmith (2021)"
        result = _remove_references_section(text)
        assert "Works Cited" not in result

    def test_numbered_references_heading(self):
        text = "Body text.\n\n9. References\n\n[1] Doe 2022"
        result = _remove_references_section(text)
        assert "[1] Doe 2022" not in result

    def test_inline_mention_preserved(self):
        """'references' in a sentence body must NOT trigger the cut."""
        text = "As described in the references section of prior work, exercise helps.\n\nReferences\n\n[1] Doe 2022"
        result = _remove_references_section(text)
        # The inline mention is before the heading, so it stays
        assert "As described in the references section" in result
        # The actual list goes
        assert "[1] Doe 2022" not in result

    def test_no_references_section_unchanged(self):
        text = "Full paper body with no reference list at the end."
        result = _remove_references_section(text)
        assert result == text


# ── _collapse_blank_lines ─────────────────────────────────────────────────────


class TestCollapseBlankLines:
    def test_three_blank_lines_become_two(self):
        text = "Para one\n\n\nPara two"
        result = _collapse_blank_lines(text)
        assert "\n\n\n" not in result

    def test_five_blank_lines_become_two(self):
        text = "Para one\n\n\n\n\nPara two"
        result = _collapse_blank_lines(text)
        assert result == "Para one\n\nPara two"

    def test_two_blank_lines_unchanged(self):
        text = "Para one\n\nPara two"
        result = _collapse_blank_lines(text)
        assert result == text


# ── clean_text (orchestrator) ─────────────────────────────────────────────────


class TestCleanText:
    def test_returns_cleaner_output_type(self):
        from rag.ingestion.models import CleanerOutput
        result = clean_text(make_input("Simple text."))
        assert isinstance(result, CleanerOutput)

    def test_doi_passed_through(self):
        result = clean_text(make_input("Simple text."))
        assert result.doi == "10.0000/test.2024.001"

    def test_evidence_availability_passed_through(self):
        result = clean_text(make_input("Simple text.", EvidenceAvailability.ABSTRACT_AVAILABLE))
        assert result.evidence_availability == EvidenceAvailability.ABSTRACT_AVAILABLE

    def test_length_fields_populated(self):
        raw = "Some raw text with  extra   spaces."
        result = clean_text(make_input(raw))
        assert result.original_length == len(raw)
        assert result.cleaned_length == len(result.clean_text)

    def test_full_pipeline_end_to_end(self):
        """Simulate a realistic noisy paper excerpt."""
        raw = (
            "Journal of Science, Vol. 10\n"
            "Exercise and Health\n"
            "Journal of Science, Vol. 10\n"
            "\n"
            "Page 1\n"
            "\n"
            "1. Introduction\n"
            "\n"
            "Regular exercise has been shown to reduce cardiovascular risk.\n"
            "\n"
            "Journal of Science, Vol. 10\n"
            "\n"
            "Page 2\n"
            "\n"
            "2. Results\n"
            "\n"
            "Participants showed a 28% reduction in heart disease incidence.\n"
            "\n"
            "\n"
            "\n"
            "References\n"
            "\n"
            "[1] Johnson et al. 2019. Cardiovascular effects of exercise.\n"
        )
        result = clean_text(make_input(raw))

        # Header stripped (appeared 3 times)
        assert "Journal of Science, Vol. 10" not in result.clean_text
        # Page numbers stripped
        assert "Page 1" not in result.clean_text
        assert "Page 2" not in result.clean_text
        # References stripped
        assert "[1] Johnson et al." not in result.clean_text
        # Real content preserved
        assert "28% reduction" in result.clean_text
        assert "Regular exercise" in result.clean_text
        # No excessive blank lines
        assert "\n\n\n" not in result.clean_text

    def test_abstract_only_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="rag.ingestion.cleaner"):
            clean_text(make_input("Abstract text only.", EvidenceAvailability.ABSTRACT_AVAILABLE))
        assert any("abstract" in record.message.lower() for record in caplog.records)
