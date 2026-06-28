from __future__ import annotations

from pathlib import Path

from app.services.reference_extraction import ReferenceExtractionService
from app.models.enums import DoiStatus

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_pdf_text"


def _read_lines(name: str) -> list[str]:
    return [line.strip() for line in (FIXTURE_DIR / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_reference_section_quality(section_name: str, expected_name: str, min_coverage: float = 0.85) -> None:
    service = ReferenceExtractionService()
    section = (FIXTURE_DIR / section_name).read_text(encoding="utf-8")
    expected_dois = set(_read_lines(expected_name))
    parsed = service.extract_references(section)
    report = service.build_doi_coverage_report(source_text=section, parsed_references=parsed)
    extracted_dois = {item.extracted_doi for item in parsed if item.doi_status == DoiStatus.FOUND.value and item.extracted_doi}
    raw_blob = "\n".join(item.raw_reference.lower() for item in parsed)

    assert report.source_doi_count == len(expected_dois)
    assert report.coverage_ratio >= min_coverage
    assert expected_dois.issubset(extracted_dois)
    assert "-preacher" not in raw_blob
    assert "employment status" not in raw_blob
    assert "welcome to the study" not in raw_blob
    assert "test510" not in raw_blob
    assert not any(str(doi).endswith("-") for doi in extracted_dois)


def test_pdf1_reference_section_recovers_expected_dois_without_footer_rows() -> None:
    _assert_reference_section_quality("pdf1_be42_reference_section.txt", "pdf1_expected_dois.txt", min_coverage=0.95)


def test_pdf2_reference_section_recovers_expected_dois_without_preacher_contamination_or_appendix_leakage() -> None:
    _assert_reference_section_quality("pdf2_be42_reference_section.txt", "pdf2_expected_dois.txt", min_coverage=0.95)


def test_pdf2_specific_line_broken_annurev_doi_is_correct() -> None:
    service = ReferenceExtractionService()
    section = (FIXTURE_DIR / "pdf2_be42_reference_section.txt").read_text(encoding="utf-8")
    parsed = service.extract_references(section)
    dois = {item.extracted_doi for item in parsed if item.extracted_doi}
    assert "10.1146/annurev-psych-120710-100452" in dois
    assert "10.1146/annurev-psych-120710-preacher" not in dois
