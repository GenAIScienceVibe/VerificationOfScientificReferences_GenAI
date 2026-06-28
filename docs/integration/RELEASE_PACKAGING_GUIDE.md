# Release Packaging Guide

This repository may be used with private research PDFs and local runtime data
during QA. Those local artifacts are not release assets and must not be copied
to public repositories, shared archives, or external services without explicit
permission from the data owner.

## Local-only artifacts

Keep the following local and private:

- real/private research PDFs, including files under
  `backend/tests/fixtures/private_pdfs/`;
- uploaded source or document PDFs under backend runtime upload folders;
- SQLite databases and database journal/WAL files;
- `.env` files containing local configuration or credentials;
- virtual environments, caches, bytecode, IDE metadata, and Git metadata;
- `local_private_artifacts/` or local backup folders;
- generated validation output and previous release archives.

The private PDF fixture folder is intentionally ignored. Existing local QA PDFs
may stay at their current paths for authorized local validation, but they must
remain untracked. Automated regression tests use sanitized text fixtures and do
not require the private PDFs.

Use `.env.example` and `backend/.env.example` as shareable configuration
templates. Never replace them with a populated `.env` file.

## Included release content

The clean release package includes source code, synthetic/text fixtures,
documentation, QA reports and findings, agent instructions, configuration
examples, and test code. It excludes private/runtime artifacts by path and file
type rather than relying only on Git tracking state.

## Scan the planned package

From the repository root:

```bash
backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only
```

The command prints the planned package path, included file count, excluded
artifact counts by category, and `unsafe_artifact_scan: PASS` only when no
unsafe path would enter the package manifest.

## Build a clean release ZIP

Build to the ignored default `release/` directory:

```bash
backend/.venv/bin/python backend/scripts/build_release_package.py
```

Or choose an output outside the repository:

```bash
backend/.venv/bin/python backend/scripts/build_release_package.py \
  --output /tmp/refcheck_ai_release.zip
```

After writing the archive, the builder scans every ZIP member using the same
unsafe-artifact rules. A safe build prints `unsafe_artifact_scan: PASS` and
returns exit code 0. A detected unsafe member prints `FAIL` and returns a
non-zero exit code.

## Verify Git tracking

Ignore rules prevent new private/runtime artifacts from being added. Existing
tracked artifacts should be removed from the index without deleting the local
files:

```bash
git rm -r --cached -- backend/data backend/tests/fixtures/private_pdfs
```

`--cached` changes tracking only. Confirm the private PDFs and databases still
exist locally if they are needed for authorized QA, then verify that tracked
unsafe files are gone:

```bash
git ls-files '*.db' '*.pdf'
git status --short
```

Do not commit, upload, or share private files merely to preserve test history.
When a shareable PDF fixture is genuinely required, create an approved
synthetic or fully sanitized fixture with documented provenance and consent.
