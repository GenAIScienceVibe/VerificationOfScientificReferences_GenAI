# QA Re-validation Report — INT-QA-011 Private Artifact Packaging

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Re-validation Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`  
Git branch: `integration/backend-rag-merge`  
Git commit tested: `86d70f20c6088bbdd2f5ad6107c04896e7061f98`

## Scope

Revalidated only INT-QA-011 — private artifact packaging risk.

No production code, test, or script was modified. INT-QA-007 and INT-QA-008
were not changed or revalidated. Both remain Open and Blocking, so this report
does not approve the full integrated release.

## Commands run

| Command | Result |
|---|---|
| `git status --short` | PASS — the expected 30 index-only removals are staged; unrelated pre-existing working-tree changes were preserved. |
| `git ls-files '*.db' '*.sqlite' '*.sqlite3' '*.pdf' '.env' 'backend/.env'` | PASS — no tracked matches. |
| Requested broad `git ls-files \| grep -E ...` marker audit | Completed with two `grep` warnings for the supplied `**pycache**` expression and filename matches containing `uploaded`; follow-up path-aware audits were used to distinguish real artifact directories from source/test names. |
| Corrected tracked-path marker audit | PASS — no tracked cache, IDE, venv, node_modules, backend runtime-data/upload directory, private-PDF directory, populated environment, database, PDF, or bytecode path. |
| Git-index audit using `classify_release_unsafe()` | PASS for INT-QA-011 categories — zero private/runtime matches; 66 historical non-Markdown validation outputs were classified `generated_validation` and are excluded from releases. |
| `git check-ignore -v --no-index` probes | PASS — populated environments, databases, runtime data/uploads, private PDFs, caches, IDE files, local backups, and release ZIPs are ignored; `.env.example` files are allowed. |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS. |
| `cd backend && .venv/bin/pytest -q tests/unit/test_release_packaging.py --tb=short` | PASS — 26 passed in 16.00s. |
| `cd backend && .venv/bin/pytest -q` | PASS — 216 passed in 142.28s. |
| `cd backend && .venv/bin/python scripts/validate_openapi.py` | PASS — 45 paths; required endpoint gaps `[]`. |
| `cd backend && .venv/bin/python scripts/run_backend_checks.py` | PASS — compile/import, 18-table initialization, and OpenAPI validation passed. |
| `cd backend && .venv/bin/python scripts/run_demo_pipeline.py` | PASS — demo completed; all endpoint calls returned HTTP 200. |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — backend 216 passed, RAG 365 passed, every check PASS, `INTEGRATED_VALIDATION_RESULT=PASS`. |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed in 1.72s. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --scan-only --root . --output /tmp/refcheck_ai_release_int011_revalidation.zip` | PASS — 316 approved files planned; unsafe scan PASS. |
| `backend/.venv/bin/python backend/scripts/build_release_package.py --root . --output /tmp/refcheck_ai_release_int011_revalidation.zip` | PASS — ZIP built with 316 approved files; unsafe scan PASS. |
| Supplied independent ZIP inspection script | PASS after interpreting intentional filename false positives — `unsafe_entries=()`, required files missing `[]`; the broad substring probe identified only validator source/test names and the allowed `backend/.env.example`. |
| Path-segment-aware independent ZIP inspection | PASS — zero unsafe entries, zero expanded required files missing, 316 archive members. |
| Post-validation Git-index and private-evidence checks | PASS — no unsafe tracked matches; 30 index removals remain staged; private PDF and local environment hashes are unchanged. |

## Unsafe artifact tracking result

**PASS.** The current Git index contains no private PDF, uploaded PDF, runtime
database, populated `.env`, cache, IDE, virtual-environment, node_modules,
backend runtime-data/upload, private-fixture, `.pyc`, or other named local
runtime artifact.

The 30 index-only removals remain staged under `backend/data/` and
`backend/tests/fixtures/private_pdfs/`. No add/modify/rename entry exists in
those roots. The audit confirmed that 17 local databases, 6 local PDFs
(including 3 private fixtures), and `backend/.env` remain on disk. Hashes of
the private PDFs and local environment were unchanged after all validation.

Both `.env.example` and `backend/.env.example` are tracked, intentionally
allowed by `.gitignore`, and included in the clean archive.

The builder also classifies and excludes 66 tracked historical generated
validation outputs. These files are not private input PDFs, uploads, runtime
databases, populated environments, caches, IDE/venv state, or backend runtime
data, and none enters the release ZIP.

## Release scan result

**PASS.** Scan-only and build modes each reported:

- included file count: 316;
- excluded artifact count: 126;
- excluded cache entries/directories: 26;
- excluded populated environment files: 1;
- excluded generated validation files: 66;
- excluded private fixture entries: 5;
- excluded runtime-data entries: 4;
- excluded runtime databases: 17;
- excluded uploaded PDFs: 3;
- excluded IDE metadata: 1;
- excluded VCS metadata: 1;
- excluded virtual environments: 2;
- `unsafe_artifact_scan: PASS`.

## Release ZIP inspection result

**PASS.** `scan_release_archive()` returned `unsafe_entries: ()`. The
path-segment-aware independent inspection found zero forbidden directory,
upload directory, populated environment, database, PDF, bytecode, or database
companion entries.

The supplied broad substring probe reported ten names because approved source
validators/tests contain the word `uploaded`; it also reported
`backend/.env.example` because its suffix expression does not exempt approved
examples. These are expected false positives, not artifact leaks. The release
classifier and corrected path-aware inspection both returned zero violations.

## Required files

**Included.** No required file was missing. The archive contains:

- root and component agent instructions;
- `.agent/shared_integrated_context.md`;
- backend and RAG source code;
- the release builder and packaging tests;
- documentation, including the release packaging guide;
- QA findings and reports, including the INT-QA-011 fixing report;
- root/backend environment examples;
- tests and synthetic/text fixtures.

Independent category counts found 96 source files, 54 test files, 19 docs
files, and 30 QA files in the 316-member archive.

## Finding result

**INT-QA-011: Fixed.** The unsafe private/runtime artifacts are absent from the
current Git index and clean archive, local private evidence remains preserved,
and both ignore rules and executable packaging controls prevent recurrence.

Finding file closed: **Yes.** Only
`qa/findings/INT-QA-011_PRIVATE_ARTIFACT_PACKAGING_RISK.md` was changed. Its
status is Closed and its blocking value is No / Resolved, with the requested
independent-QA closure note.

## Regression results

- Backend regression: **PASS** — 216 tests.
- RAG regression: **PASS** — 365 tests.
- OpenAPI/check/demo: **PASS** — 45 paths, no endpoint gaps, backend checks
  completed, and demo calls returned HTTP 200.
- Integrated runner: **PASS** — `INTEGRATED_VALIDATION_RESULT=PASS`.

## Remaining risks

- Existing Git history may still contain the previously tracked private and
  runtime artifacts. No history rewrite was attempted; remediation is a
  separate destructive governance decision requiring data-owner review.
- The staged index removals must be included in the eventual authorized commit
  for the clean tracking state to persist beyond this workspace/index.
- Private PDFs retained locally remain subject to consent, filesystem access,
  retention, and sharing controls.
- The release builder intentionally excludes every PDF. Any future approved
  synthetic PDF fixture requires an explicit reviewed policy change.
- INT-QA-007 and INT-QA-008 remain Open and Blocking. Full integrated release
  approval remains withheld.

## Final decision

**PASS** for INT-QA-011 re-validation. Full integrated release approval is not
granted because INT-QA-007 and INT-QA-008 remain open blocking findings.
