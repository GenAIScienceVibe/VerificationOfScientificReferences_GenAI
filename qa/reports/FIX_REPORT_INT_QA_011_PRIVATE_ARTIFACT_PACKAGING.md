# Fixing Report — INT-QA-011 Private Artifact Packaging

Run date: 2026-06-28 (Asia/Singapore)  
Role: Fixing Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Finding addressed

INT-QA-011 — Private artifact packaging risk.

No other finding was fixed or closed. INT-QA-007 and INT-QA-008 remain outside
this fixing scope.

## Root cause

The repository had private PDF fixtures, uploaded source PDFs, and runtime
SQLite databases in the Git index. The existing ignore rules covered only a
small subset of backend runtime paths and did not protect private fixture PDFs,
all databases, local environments, IDE metadata, release archives, or other
common local-only artifacts.

There was also no deterministic release builder or post-build archive scan.
Consequently, creating a release by copying the working tree could include
private research material, runtime state, credentials, caches, and generated
validation output even when some paths happened to be untracked.

## Unsafe artifacts found

- 17 tracked SQLite `.db` files under `backend/data/`.
- 3 tracked uploaded PDFs under a backend runtime upload directory.
- 3 tracked private research PDF fixtures under
  `backend/tests/fixtures/private_pdfs/`.
- 7 tracked placeholder/documentation paths inside those two local-only roots.
- One populated local `backend/.env` file (untracked and preserved locally).
- Local virtual environments, Python/test caches, `.idea/`, generated
  validation output, Git metadata, and runtime upload/data directories.

No private file contents or credential values were printed, copied into the
report, or added to the release package.

## Files changed

- `.gitignore`
- `backend/scripts/build_release_package.py`
- `backend/tests/unit/test_release_packaging.py`
- `docs/integration/RELEASE_PACKAGING_GUIDE.md`
- `qa/reports/FIX_REPORT_INT_QA_011_PRIVATE_ARTIFACT_PACKAGING.md`

No production application/RAG code, existing test, API route, API contract, or
finding file was modified.

## Files removed from Git tracking

`git rm -r --cached` staged index-only removal of 30 paths:

- all 25 previously tracked paths under `backend/data/`, comprising 17
  databases, 3 uploaded PDFs, and 5 placeholders;
- all 5 previously tracked paths under
  `backend/tests/fixtures/private_pdfs/`, comprising 3 private PDFs, the local
  fixture README, and one placeholder.

All 17 databases, all 6 PDFs, the local fixture README, and `backend/.env` were
confirmed to remain on disk after index cleanup and after the validation runs.
A local preservation archive was kept outside the repository in `/tmp` while
validation ran. `git ls-files` now returns no tracked database, PDF, populated
`.env`, IDE, bytecode, or cache paths.

## Ignore-rule changes

`.gitignore` now excludes:

- populated `.env` variants while explicitly allowing `.env.example` and
  `.env.sample` templates;
- all common SQLite database forms and journal/WAL companions;
- backend runtime data, uploads, uploaded-PDF, and source-PDF directories;
- the private PDF fixture directory and designated local backup directories;
- Python/test/tool caches, virtual environments, IDE metadata, release output,
  ZIP archives, and common system metadata.

The new rules prevent future accidental additions; the index cleanup handles
artifacts that were already tracked.

## Release builder and scanner

`backend/scripts/build_release_package.py` builds a deterministic ZIP from an
allowable working-tree manifest and supports a non-writing `--scan-only` mode.
It excludes private PDFs, every other PDF artifact, runtime uploads/data,
databases, populated environment files, local backups, caches, virtual
environments, IDE/VCS metadata, generated validation output, old release
archives, runtime logs/coverage, and symlinks.

The builder validates both the planned manifest and every written ZIP member.
It returns a non-zero result if an unsafe member is detected. Source code,
tests, synthetic/text fixtures, documentation, QA records, agent instructions,
and configuration examples remain eligible for the release.

The final clean package was built outside the repository at
`/tmp/refcheck_ai_release_int011.zip`. It contains 316 approved files, records
126 local/private exclusion counters, and returns
`unsafe_artifact_scan: PASS`. An independent member scan found zero unsafe
entries and confirmed required source, documentation, QA, and agent instruction
files were present.

## Tests added

`backend/tests/unit/test_release_packaging.py` adds 26 tests covering:

- classification of environment secrets, databases, private/uploaded/other
  PDFs, caches, IDE/VCS metadata, local backups, release output, and generated
  validation files;
- preservation of source, docs, QA reports, agent instructions, and environment
  examples;
- clean archive construction and required-file inclusion;
- deliberate unsafe archive/path detection;
- exclusion of phase-specific uploaded-PDF directories.

No failing test was removed or weakened.

## Documentation added

`docs/integration/RELEASE_PACKAGING_GUIDE.md` documents local-only data,
approved release content, scan/build commands, Git index cleanup, local
evidence preservation, and the requirement to use approved synthetic or fully
sanitized fixtures for shareable PDF tests.

## Commands run

| Command | Result |
|---|---|
| Private/runtime filesystem and Git-index inventory (`find`, `rg`, `git ls-files`, `git status`) | PASS — unsafe categories and tracking state recorded without reading private contents. |
| `git rm -r --cached -- backend/data backend/tests/fixtures/private_pdfs` | PASS — 30 paths removed from the index only; local files preserved. |
| `git check-ignore -v --no-index` probes for `.env`, DB, PDF, cache, IDE, release, and example paths | PASS — unsafe samples ignored; environment examples allowed. |
| `cd backend && .venv/bin/python -m pytest -q tests/unit/test_release_packaging.py --tb=short` | PASS — 26 passed in 14.38s. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_int011_final.zip` | PASS — planned manifest scan returned PASS. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_int011.zip` | PASS — final clean ZIP contains 316 approved files, records 126 exclusion counters, and returns unsafe scan PASS. |
| Independent ZIP member scan and required-file check | PASS — zero unsafe entries; required files present. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q` | PASS — 216 passed in 132.76s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI checks passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed and all endpoint calls returned 200. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.61s. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 216 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| Post-validation local preservation and `git ls-files` checks | PASS — local private/runtime evidence remains present; no unsafe artifact remains tracked. |

## Pass/fail result

**PASS.** Private/runtime artifacts are no longer tracked, remain available for
authorized local QA, and are blocked by both ignore rules and the release
builder. Packaging tests, full backend/RAG regressions, OpenAPI/check/demo, and
integrated validation all passed.

## Remaining risks

- Index cleanup prevents the next commit from retaining these artifacts but
  does not erase them from existing Git history. History rewriting is a
  separate, destructive governance action requiring data-owner review and was
  not performed.
- Private local PDFs still require normal filesystem, consent, retention, and
  sharing controls. Ignoring them does not grant permission to distribute them.
- The release builder intentionally excludes every PDF. A future approved
  synthetic PDF fixture would need an explicit, reviewed packaging policy
  change.
- Generated validation artifacts remain available locally but are excluded
  from the clean release; reproducible commands are included instead.
- INT-QA-011 remains Open until an independent QA Re-validation Agent confirms
  the fix. Other open findings remain unaffected.

## Ready for QA revalidation

**Yes.**
