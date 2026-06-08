from __future__ import annotations

from app.services.reference_extraction import ReferenceExtractionService
from app.services.text_processing import repair_doi_line_continuations
from app.models.enums import DoiStatus


def test_repair_doi_line_continuation_with_numeric_suffix() -> None:
    text = "https://doi.org/10.1111/j.1467-\n9280.2007.01882.x"
    repaired = repair_doi_line_continuations(text)
    assert "10.1111/j.1467-9280.2007.01882.x" in repaired


def test_repair_doi_line_continuation_does_not_consume_next_author() -> None:
    text = "https://doi.org/10.1146/annurev-psych-120710-\nPreacher, K. J., & Hayes, A. F. (2004)."
    repaired = repair_doi_line_continuations(text)
    assert "10.1146/annurev-psych-120710-Preacher" not in repaired
    assert "Preacher, K. J." in repaired


def test_doi_only_url_line_attaches_to_previous_reference() -> None:
    service = ReferenceExtractionService()
    section = """
Smith, J. (2024). A paper title. Journal of Demo Studies, 12(1), 1-10.
https://doi.org/10.1234/demo.2024
"""
    refs = service.extract_references(section)
    assert len(refs) == 1
    assert refs[0].extracted_doi == "10.1234/demo.2024"
    assert refs[0].doi_status == DoiStatus.FOUND.value


def test_journal_volume_continuation_with_doi_attaches_to_previous_reference() -> None:
    service = ReferenceExtractionService()
    section = """
Mitschelen, A., & Kauffeld, S. (2025). Workplace learning during organizational onboarding: Integrating formal, informal, and self-regulated workplace learning. Frontiers in
Organizational Psychology, 3, 1569098. https://doi.org/10.3389/forgp.2025.1569098
"""
    refs = service.extract_references(section)
    assert len(refs) == 1
    assert refs[0].raw_reference.startswith("Mitschelen")
    assert "Organizational Psychology" in refs[0].raw_reference
    assert refs[0].extracted_doi == "10.3389/forgp.2025.1569098"


def test_final_reference_rescan_finds_doi_after_merging() -> None:
    service = ReferenceExtractionService()
    section = """
Olafsen, A. H., Halvari, H., & Frølund, C. W. (2021). The Basic Psychological Need Satisfaction and Need Frustration at Work Scale: A validation study. Frontiers in
Psychology, 12, 697306.
https://doi.org/10.3389/fpsyg.2021.697306
"""
    refs = service.extract_references(section)
    assert len(refs) == 1
    assert refs[0].extracted_doi == "10.3389/fpsyg.2021.697306"


def test_doi_coverage_report_detects_missing_doi() -> None:
    service = ReferenceExtractionService()
    section = """
Smith, J. (2024). Demo. Journal. https://doi.org/10.1234/demo.2024
Lee, A. (2023). Demo two. Journal. https://doi.org/10.9999/demo.2023
"""
    parsed = service.extract_references("Smith, J. (2024). Demo. Journal. https://doi.org/10.1234/demo.2024")
    report = service.build_doi_coverage_report(source_text=section, parsed_references=parsed)
    assert report.source_doi_count == 2
    assert report.extracted_doi_count == 1
    assert report.coverage_ratio == 0.5
    assert "10.9999/demo.2023" in report.missing_from_extracted


def test_no_author_name_contamination_in_doi() -> None:
    service = ReferenceExtractionService()
    result = service.extract_doi(
        "Podsakoff, P. (2011). Annual Review. https://doi.org/10.1146/annurev-psych-120710-Preacher, K. J. (2004)."
    )
    assert result.doi_status == DoiStatus.MALFORMED.value
    assert result.extracted_doi != "10.1146/annurev-psych-120710-preacher"
