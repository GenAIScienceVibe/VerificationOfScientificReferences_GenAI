# INT-QA-011 — Private artifact packaging risk

Finding ID: INT-QA-011  
Title: Private PDFs, runtime databases, and uploaded PDFs are tracked in the repository  
Severity: P1  
Status: Closed  
Blocking: No / Resolved  
Component: Docs / Other  
Phase impacted: Integrated QA  
Endpoint/service: Repository packaging  
Test type: Manual / Security

## Problem

Files explicitly described as private, plus populated SQLite databases and uploaded PDF artifacts, are tracked. Existing ignore rules do not cover `backend/data/*.db` or private fixture PDFs.

## Steps to reproduce

```bash
git ls-files 'backend/data/*.db' 'backend/data/**/*.pdf' 'backend/tests/fixtures/private_pdfs/*.pdf'
```

## Expected result

Shareable packages exclude private PDFs, populated DBs, uploaded files, local caches, secrets, and IDE state; fixtures are synthetic/sanitized and documented.

## Actual result

Git lists 17 SQLite DB files, three uploaded PDF artifacts, and all three `private_pdfs` fixtures. `.gitignore` ignores `backend/*.db`, not nested `backend/data/*.db`, and has no private-PDF rule. `backend/.env` is correctly ignored and was not tracked; `.pytest_cache` is ignored.

## Evidence

Tracked-file inventory on commit `86d70f20c6088bbdd2f5ad6107c04896e7061f98`.

## Root cause hypothesis

Historical validation outputs were committed and ignore rules do not match the actual nested runtime-data locations.

## Suggested fix direction

Review ownership/consent, replace private fixtures with approved synthetic/sanitized assets, remove runtime artifacts from distribution history as appropriate, and tighten packaging/ignore rules.

## Regression risk

High privacy and data-governance risk. Removal must preserve approved QA reproducibility through a private local fixture process.

## Validation required after fix

Run a tracked-file and packaged-archive scan for secrets, PDFs, DBs, cache, IDE, and upload artifacts.

## Closure note

Closed after independent QA re-validation. Private PDFs, uploaded PDFs, runtime databases, `.env`, cache/IDE/venv files, and local runtime artifacts are excluded from tracking and from the clean release package. The release scanner and builder passed with zero unsafe archive entries. Packaging tests, full backend regression, full RAG regression, OpenAPI/check/demo, and integrated validation passed. Existing Git history may still contain prior artifacts and remains a separate governance risk.
