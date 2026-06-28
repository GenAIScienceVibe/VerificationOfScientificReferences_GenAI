from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_ARCHIVE_NAME = "refcheck_ai_release.zip"

_VCS_DIRS = {".git", ".hg", ".svn"}
_IDE_DIRS = {".idea", ".vscode"}
_CACHE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".tox",
    ".nox",
    "htmlcov",
}
_VENV_DIRS = {".venv", "venv", "env", "__pypackages__", "node_modules"}
_LOCAL_ONLY_DIRS = {
    "local_private_artifacts",
    "local_backups",
    ".local_backups",
}
_RELEASE_OUTPUT_DIRS = {"release", "releases", "dist", "build"}
_UPLOAD_DIR_MARKERS = {
    "uploads",
    "uploaded_pdfs",
    "uploaded_pdf_uploads",
    "reference_source_pdfs",
}
_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_DATABASE_TRAILERS = (".db-journal", ".db-shm", ".db-wal")

_PRUNED_CATEGORIES = {
    "cache",
    "ide_metadata",
    "local_private_backup",
    "release_output",
    "vcs_metadata",
    "virtual_environment",
}


@dataclass(frozen=True)
class ReleaseManifest:
    included_files: tuple[Path, ...]
    excluded_counts: dict[str, int]


@dataclass(frozen=True)
class ReleaseBuildResult:
    output_path: Path
    included_count: int
    excluded_counts: dict[str, int]
    unsafe_entries: tuple[tuple[str, str], ...]


def _normalized_relative_path(path: str | Path) -> PurePosixPath:
    value = str(path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return PurePosixPath(value or ".")


def classify_release_unsafe(path: str | Path, *, is_dir: bool = False) -> str | None:
    """Return the exclusion category for a repository-relative path."""
    relative = _normalized_relative_path(path)
    parts = tuple(part.casefold() for part in relative.parts if part not in {"", "."})
    if not parts:
        return None

    name = parts[-1]
    suffix = PurePosixPath(name).suffix.casefold()
    directory_parts = parts if is_dir else parts[:-1]
    has_upload_directory = any(
        part in _UPLOAD_DIR_MARKERS or "upload" in part
        for part in directory_parts
    )

    if any(part in _VCS_DIRS for part in parts):
        return "vcs_metadata"
    if any(part in _IDE_DIRS for part in parts):
        return "ide_metadata"
    if any(part in _CACHE_DIRS for part in parts) or suffix in {".pyc", ".pyo"}:
        return "cache"
    if any(part in _VENV_DIRS for part in parts):
        return "virtual_environment"
    if any(part in _LOCAL_ONLY_DIRS for part in parts):
        return "local_private_backup"
    if any(part in _RELEASE_OUTPUT_DIRS for part in parts):
        return "release_output"

    if name == ".env" or (
        name.startswith(".env.") and name not in {".env.example", ".env.sample"}
    ):
        return "environment_secret"
    if name in {".ds_store", "thumbs.db"}:
        return "system_metadata"

    if "private_pdfs" in parts:
        return "private_pdf_fixture"
    if suffix == ".pdf" and has_upload_directory:
        return "uploaded_pdf"
    if suffix == ".pdf":
        return "pdf_artifact"

    if suffix in _DATABASE_SUFFIXES or name.endswith(_DATABASE_TRAILERS):
        return "runtime_database"
    if len(parts) >= 2 and parts[0] == "backend" and parts[1] == "data":
        return "runtime_data"
    if has_upload_directory:
        return "uploaded_data"

    if suffix == ".zip":
        return "release_archive"
    if suffix == ".log" or name in {".coverage", "coverage.xml"}:
        return "runtime_output"

    if len(parts) >= 2 and parts[0] == "backend" and parts[1] == "validation":
        if suffix != ".md":
            return "generated_validation"
    if relative.as_posix().casefold() == "backend/validation_be6_tmp.txt":
        return "generated_validation"

    if is_dir and name.startswith(".") and name.endswith("_cache"):
        return "cache"
    return None


def collect_release_manifest(
    root: Path,
    *,
    output_path: Path | None = None,
) -> ReleaseManifest:
    """Collect safe files and count excluded local/private artifacts."""
    root = root.resolve()
    resolved_output = output_path.resolve() if output_path is not None else None
    included: list[Path] = []
    excluded: Counter[str] = Counter()

    for current_dir, dir_names, file_names in os.walk(root, topdown=True):
        current = Path(current_dir)
        kept_directories: list[str] = []
        for directory_name in sorted(dir_names):
            directory = current / directory_name
            relative = directory.relative_to(root)
            category = classify_release_unsafe(relative, is_dir=True)
            if category in _PRUNED_CATEGORIES:
                excluded[category] += 1
            else:
                kept_directories.append(directory_name)
        dir_names[:] = kept_directories

        for file_name in sorted(file_names):
            file_path = current / file_name
            relative = file_path.relative_to(root)
            if file_path.is_symlink():
                excluded["symlink"] += 1
                continue
            if resolved_output is not None and file_path.resolve() == resolved_output:
                excluded["release_archive"] += 1
                continue
            category = classify_release_unsafe(relative)
            if category is not None:
                excluded[category] += 1
                continue
            included.append(relative)

    return ReleaseManifest(
        included_files=tuple(sorted(included, key=lambda item: item.as_posix())),
        excluded_counts=dict(sorted(excluded.items())),
    )


def scan_release_paths(paths: Iterable[str | Path]) -> tuple[tuple[str, str], ...]:
    violations: list[tuple[str, str]] = []
    for path in paths:
        relative = _normalized_relative_path(path).as_posix()
        category = classify_release_unsafe(relative)
        if category is not None:
            violations.append((relative, category))
    return tuple(sorted(violations))


def scan_release_archive(archive_path: Path) -> tuple[tuple[str, str], ...]:
    with ZipFile(archive_path) as archive:
        return scan_release_paths(archive.namelist())


def build_release_package(root: Path, output_path: Path) -> ReleaseBuildResult:
    root = root.resolve()
    output_path = output_path.resolve()
    manifest = collect_release_manifest(root, output_path=output_path)
    planned_violations = scan_release_paths(manifest.included_files)
    if planned_violations:
        raise RuntimeError(f"Unsafe files entered the release manifest: {planned_violations!r}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative in manifest.included_files:
            archive.write(root / relative, arcname=relative.as_posix())

    archive_violations = scan_release_archive(output_path)
    return ReleaseBuildResult(
        output_path=output_path,
        included_count=len(manifest.included_files),
        excluded_counts=manifest.excluded_counts,
        unsafe_entries=archive_violations,
    )


def _print_summary(
    *,
    output_path: Path,
    included_count: int,
    excluded_counts: dict[str, int],
    unsafe_entries: tuple[tuple[str, str], ...],
    scan_only: bool,
) -> None:
    print(f"output_package_path: {output_path}")
    print(f"package_created: {not scan_only}")
    print(f"included_file_count: {included_count}")
    print(f"excluded_artifact_count: {sum(excluded_counts.values())}")
    for category, count in sorted(excluded_counts.items()):
        print(f"excluded_{category}: {count}")
    if unsafe_entries:
        print("unsafe_artifact_scan: FAIL")
        for path, category in unsafe_entries:
            print(f"unsafe_entry: {category}: {path}")
    else:
        print("unsafe_artifact_scan: PASS")


def main() -> int:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Build or scan a release package that excludes private/runtime artifacts."
    )
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Print exclusions and validate the planned manifest without creating a zip.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = (
        args.output.resolve()
        if args.output is not None
        else root / "release" / DEFAULT_ARCHIVE_NAME
    )

    if args.scan_only:
        manifest = collect_release_manifest(root, output_path=output)
        unsafe_entries = scan_release_paths(manifest.included_files)
        _print_summary(
            output_path=output,
            included_count=len(manifest.included_files),
            excluded_counts=manifest.excluded_counts,
            unsafe_entries=unsafe_entries,
            scan_only=True,
        )
        return 1 if unsafe_entries else 0

    result = build_release_package(root, output)
    _print_summary(
        output_path=result.output_path,
        included_count=result.included_count,
        excluded_counts=result.excluded_counts,
        unsafe_entries=result.unsafe_entries,
        scan_only=False,
    )
    return 1 if result.unsafe_entries else 0


if __name__ == "__main__":
    raise SystemExit(main())
