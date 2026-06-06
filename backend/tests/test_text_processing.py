from __future__ import annotations

from app.services.text_processing import clean_text, detect_basic_sections


SAMPLE = """Sample Paper\n\nAbstract\nThis study cites (Smith, 2023) and keeps DOI 10.1234/demo.2023.\n\nIntroduction\nThe introduction keeps [1] style citations.\n\nReferences\nSmith, J. (2023). Demo. doi:10.1234/demo.2023\n"""


def test_clean_text_preserves_doi_and_citations() -> None:
    cleaned = clean_text("Sample\r\n\r\n" + SAMPLE + "\n\n\n")
    assert "10.1234/demo.2023" in cleaned
    assert "(Smith, 2023)" in cleaned
    assert "[1]" in cleaned
    assert "\r" not in cleaned


def test_section_detection_finds_abstract_and_references() -> None:
    sections = detect_basic_sections(clean_text(SAMPLE))
    names = {section.name for section in sections}
    assert "Title" in names
    assert "Abstract" in names
    assert "Introduction" in names
    assert "References" in names
