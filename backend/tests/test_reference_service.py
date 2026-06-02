"""
Unit tests for BE-3 Reference Extraction Service
SCRUM-task: Add unit tests for DOI extraction
"""
import pytest
from app.services.reference_service import (
    extract_doi,
    normalize_doi,
    split_references,
    extract_year,
    extract_title,
    extract_authors,
)
from app.db.models import DoiStatus


# ---------------------------------------------------------------------------
# DOI extraction tests
# ---------------------------------------------------------------------------

class TestExtractDoi:

    def test_doi_found_standard(self):
        text = "Smith J. et al. Title. Journal. https://doi.org/10.1000/xyz123"
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert doi == "10.1000/xyz123"

    def test_doi_found_bare(self):
        text = "Smith J. Title. DOI: 10.1038/nature12345"
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert doi == "10.1038/nature12345"

    def test_doi_found_in_url(self):
        text = "Available at https://doi.org/10.1073/pnas.2414972121"
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert doi == "10.1073/pnas.2414972121"

    def test_doi_found_normalized_lowercase(self):
        text = "doi:10.1016/J.ENVPOL.2021.115931"
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert doi == doi.lower()

    def test_doi_missing(self):
        text = "Smith J. Title. Journal of Science. 2020."
        doi, status = extract_doi(text)
        assert status == DoiStatus.MISSING
        assert doi is None

    def test_doi_malformed_no_slash(self):
        text = "Reference with bad doi: 10.1234 no slash"
        doi, status = extract_doi(text)
        # No slash means it won't match full DOI pattern
        assert status == DoiStatus.MISSING

    def test_doi_strips_trailing_punctuation(self):
        text = "Smith J. Title. https://doi.org/10.1000/xyz123."
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert not doi.endswith('.')

    def test_doi_with_complex_suffix(self):
        text = "Available at doi:10.1145/3292500.3330777 [CrossRef]"
        doi, status = extract_doi(text)
        assert status == DoiStatus.FOUND
        assert doi == "10.1145/3292500.3330777"


# ---------------------------------------------------------------------------
# DOI normalization tests
# ---------------------------------------------------------------------------

class TestNormalizeDoi:

    def test_strips_https_prefix(self):
        assert normalize_doi("https://doi.org/10.1000/xyz") == "10.1000/xyz"

    def test_strips_http_prefix(self):
        assert normalize_doi("http://doi.org/10.1000/xyz") == "10.1000/xyz"

    def test_strips_doi_colon(self):
        assert normalize_doi("doi:10.1000/xyz") == "10.1000/xyz"

    def test_lowercase(self):
        assert normalize_doi("10.1000/XYZ") == "10.1000/xyz"

    def test_strips_trailing_period(self):
        assert normalize_doi("10.1000/xyz.") == "10.1000/xyz"

    def test_strips_whitespace(self):
        assert normalize_doi("  10.1000/xyz  ") == "10.1000/xyz"


# ---------------------------------------------------------------------------
# Reference splitting tests
# ---------------------------------------------------------------------------

class TestSplitReferences:

    def test_numbered_dot(self):
        text = """1. Smith J. Title one. Journal. 2020.
2. Doe A. Title two. Conference. 2021.
3. Jones E. Title three. Book. 2022."""
        refs = split_references(text)
        assert len(refs) == 3
        assert refs[0].startswith("1.")
        assert refs[1].startswith("2.")

    def test_numbered_bracket(self):
        text = """[1] Smith J. Title one. Journal. 2020.
[2] Doe A. Title two. Conference. 2021."""
        refs = split_references(text)
        assert len(refs) == 2

    def test_strips_header(self):
        text = """References
1. Smith J. Title. 2020.
2. Doe A. Title. 2021."""
        refs = split_references(text)
        assert len(refs) == 2
        assert not any(r.strip().lower() == "references" for r in refs)

    def test_paragraph_based_fallback(self):
        text = """Smith J. Title one. Journal of Science. 2020.

Doe A. Title two. Conference Proceedings. 2021."""
        refs = split_references(text)
        assert len(refs) == 2

    def test_single_reference(self):
        text = "1. Smith J. Only Reference. Journal. 2020. doi:10.1000/xyz"
        refs = split_references(text)
        assert len(refs) == 1


# ---------------------------------------------------------------------------
# Year extraction tests
# ---------------------------------------------------------------------------

class TestExtractYear:

    def test_year_in_parens(self):
        assert extract_year("Smith J. (2020). Title.") == 2020

    def test_year_at_end(self):
        assert extract_year("Smith J. Title. Journal. 2021.") == 2021

    def test_year_not_found(self):
        assert extract_year("No year here.") is None

    def test_year_range_takes_first(self):
        assert extract_year("Work from 2019-2021.") == 2019


# ---------------------------------------------------------------------------
# Title extraction tests
# ---------------------------------------------------------------------------

class TestExtractTitle:

    def test_quoted_title(self):
        text = '1. Smith J. "The effects of X on Y." Journal. 2020.'
        title = extract_title(text)
        assert title == "The effects of X on Y."

    def test_title_after_period(self):
        text = "1. Smith J. Effects of AI on transport. Journal. 2020."
        title = extract_title(text)
        assert title is not None
        assert len(title) > 5


# ---------------------------------------------------------------------------
# Author extraction tests
# ---------------------------------------------------------------------------

class TestExtractAuthors:

    def test_single_author(self):
        text = "1. Smith, J. Title. Journal. 2020."
        authors = extract_authors(text)
        assert authors is not None
        assert len(authors) >= 1

    def test_multiple_authors_semicolon(self):
        text = "1. Smith, J.; Doe, A.; Jones, E. Title of the paper. Journal. 2020."
        authors = extract_authors(text)
        assert authors is not None
        assert len(authors) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
