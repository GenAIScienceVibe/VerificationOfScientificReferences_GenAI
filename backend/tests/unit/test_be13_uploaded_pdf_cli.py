from __future__ import annotations

from pathlib import Path

from scripts.validate_uploaded_pdfs_be13 import collect_pdf_paths


def test_collect_pdf_paths_accepts_pdf_dir(tmp_path: Path) -> None:
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.PDF"
    ignored = tmp_path / "notes.txt"
    first.write_bytes(b"%PDF-1.4")
    second.write_bytes(b"%PDF-1.4")
    ignored.write_text("not a pdf", encoding="utf-8")

    paths, error = collect_pdf_paths(pdf_dir=tmp_path, pdfs=[])

    assert error is None
    assert paths == [first, second]


def test_collect_pdf_paths_reports_missing_or_empty_pdf_dir(tmp_path: Path) -> None:
    missing_paths, missing_error = collect_pdf_paths(pdf_dir=tmp_path / "missing", pdfs=[])
    empty_paths, empty_error = collect_pdf_paths(pdf_dir=tmp_path, pdfs=[])

    assert missing_paths == []
    assert "PDF directory not found" in str(missing_error)
    assert empty_paths == []
    assert "No PDF files found" in str(empty_error)

