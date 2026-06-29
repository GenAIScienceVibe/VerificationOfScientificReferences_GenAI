from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_release_package import (
    build_release_package,
    classify_release_unsafe,
    scan_release_archive,
    scan_release_paths,
)


@pytest.mark.parametrize(
    ("path", "expected_category"),
    [
        pytest.param(".env", "environment_secret", id="root-env"),
        pytest.param("backend/.env", "environment_secret", id="backend-env"),
        pytest.param("backend/data/runtime.db", "runtime_database", id="database"),
        pytest.param(
            "backend/tests/fixtures/private_pdfs/paper.pdf",
            "private_pdf_fixture",
            id="private-pdf",
        ),
        pytest.param(
            "backend/data/uploads/source.pdf",
            "uploaded_pdf",
            id="uploaded-pdf",
        ),
        pytest.param(
            "backend/data/be11_uploaded_pdf_uploads/source.pdf",
            "uploaded_pdf",
            id="phase-uploaded-pdf",
        ),
        pytest.param("docs/research.pdf", "pdf_artifact", id="other-pdf"),
        pytest.param("pkg/__pycache__/module.pyc", "cache", id="pycache"),
        pytest.param(".pytest_cache/v/cache/nodeids", "cache", id="pytest-cache"),
        pytest.param(".mypy_cache/state.json", "cache", id="mypy-cache"),
        pytest.param(".ruff_cache/state.json", "cache", id="ruff-cache"),
        pytest.param(".idea/workspace.xml", "ide_metadata", id="idea"),
        pytest.param(".git/HEAD", "vcs_metadata", id="git"),
        pytest.param(
            "local_private_artifacts/original.pdf",
            "local_private_backup",
            id="local-private",
        ),
        pytest.param("release/old-release.zip", "release_output", id="release-output"),
        pytest.param(
            "backend/validation/openapi_generated.json",
            "generated_validation",
            id="generated-openapi",
        ),
    ],
)
def test_scanner_classifies_release_unsafe_paths(
    path: str,
    expected_category: str,
) -> None:
    assert classify_release_unsafe(path) == expected_category


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "backend/.env.example",
        "app/main.py",
        "docs/integration/guide.md",
        "qa/reports/report.md",
        ".agent/shared_integrated_context.md",
        "AGENTS.md",
    ],
)
def test_scanner_allows_required_release_files(path: str) -> None:
    assert classify_release_unsafe(path) is None


def _write(root: Path, relative: str, content: bytes = b"safe") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_release_package_excludes_private_artifacts_and_keeps_required_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repository"
    safe_files = {
        "app/main.py",
        "docs/integration/RELEASE_PACKAGING_GUIDE.md",
        "qa/reports/QA_REPORT.md",
        ".agent/shared_integrated_context.md",
        "AGENTS.md",
        ".env.example",
        "backend/.env.example",
    }
    for relative in safe_files:
        _write(root, relative)

    unsafe_files = {
        ".env",
        "backend/.env",
        "backend/data/runtime.db",
        "backend/data/uploads/source.pdf",
        "backend/tests/fixtures/private_pdfs/private.pdf",
        "docs/research.pdf",
        "pkg/__pycache__/module.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".mypy_cache/state.json",
        ".ruff_cache/state.json",
        ".idea/workspace.xml",
        ".git/HEAD",
        "local_private_artifacts/original.pdf",
        "release/old-release.zip",
        "backend/validation/openapi_generated.json",
    }
    for relative in unsafe_files:
        _write(root, relative)

    output = tmp_path / "release.zip"
    result = build_release_package(root, output)

    with ZipFile(output) as archive:
        names = set(archive.namelist())

    assert safe_files <= names
    assert not (unsafe_files & names)
    assert result.included_count == len(safe_files)
    assert result.unsafe_entries == ()
    assert scan_release_archive(output) == ()
    assert result.excluded_counts["environment_secret"] == 2
    assert result.excluded_counts["runtime_database"] == 1
    assert result.excluded_counts["private_pdf_fixture"] == 1
    assert result.excluded_counts["uploaded_pdf"] == 1


def test_scanner_catches_intentionally_unsafe_archive_entries(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("app/main.py", "safe")
        archive.writestr(".env", "SECRET=value")
        archive.writestr("backend/data/runtime.db", "runtime")
        archive.writestr("backend/tests/fixtures/private_pdfs/private.pdf", "pdf")

    violations = scan_release_archive(archive_path)

    assert (".env", "environment_secret") in violations
    assert ("backend/data/runtime.db", "runtime_database") in violations
    assert (
        "backend/tests/fixtures/private_pdfs/private.pdf",
        "private_pdf_fixture",
    ) in violations


def test_path_scanner_reports_unsafe_samples_only() -> None:
    violations = scan_release_paths(
        [
            "app/main.py",
            "docs/guide.md",
            ".env",
            "backend/data/runtime.db",
            "backend/data/uploads/source.pdf",
        ]
    )

    assert violations == (
        (".env", "environment_secret"),
        ("backend/data/runtime.db", "runtime_database"),
        ("backend/data/uploads/source.pdf", "uploaded_pdf"),
    )
