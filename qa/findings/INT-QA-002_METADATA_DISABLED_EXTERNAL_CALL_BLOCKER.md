# INT-QA-002 — Metadata-disabled external call blocker

Finding ID: INT-QA-002  
Title: Title-based metadata providers are called while metadata lookup is disabled  
Severity: P1  
Status: Closed  
Blocking: Yes  
Component: Metadata  
Phase impacted: BE5 / BE14 / Integrated QA  
Endpoint/service: `MetadataLookupService._verify_reference`  
Test type: Integration / Real PDF / Manual

## Problem

`METADATA_LOOKUP_ENABLED=false` does not block all external metadata activity. References without a DOI but with a title enter the title-search chain before the disabled-mode guard.

## Steps to reproduce

```bash
cd backend
METADATA_LOOKUP_ENABLED=false .venv/bin/python scripts/validate_uploaded_pdfs_be13.py --pdf-dir tests/fixtures/private_pdfs
```

Also inspect `backend/app/services/doi_metadata_lookup.py` lines 349-405 and 496-505.

## Expected result

No CrossRef, OpenAlex, Semantic Scholar, CORE, Unpaywall, arXiv/full-text, title DOI, or related external provider method is called when metadata lookup is disabled.

## Actual result

The three-PDF validator logs repeated `title_search_no_confident_match` entries for three title providers while `METADATA_LOOKUP_ENABLED=false`; several sequences took about three seconds. The code constructs and invokes CrossRef, OpenAlex, Semantic Scholar, and optionally CORE title searchers before reaching the disabled guard. DOI-based CrossRef and downstream OpenAlex/Semantic Scholar/SSRN/Unpaywall/arXiv/CORE paths are behind the later guard, but title lookup is not.

## Evidence

- `doi_metadata_lookup.py:349-405`: title search executes when normalized DOI is absent.
- `doi_metadata_lookup.py:496-505`: disabled guard occurs only after title search and DOI syntax/cache handling.
- Mock real-PDF validation output contains repeated title-search calls while disabled.
- Controlled disabled-mode pytest run produced 125 passes and 5 BE5 failures and showed the same provider activity in captured logs.

## Root cause hypothesis

The feature flag was added around DOI-based lookup but not placed at the entry to every external-resolution path.

## Suggested fix direction

Apply the disabled guard before title resolution and any other external provider selection; add call-count regression tests covering all providers and DOI/no-DOI cases.

## Regression risk

High. Offline validation can leak bibliographic data, make unintended network calls, and become nondeterministic.

## Validation required after fix

Use strict mocks that fail on any CrossRef, OpenAlex, Semantic Scholar, CORE, Unpaywall, SSRN, arXiv/PDF, or title-search call with the flag false.

## Closure note

Closed after independent re-validation on 2026-06-28. Focused disabled-mode
tests passed for references with and without a DOI. Strict fail-on-call spies
proved that CrossRef, OpenAlex, Semantic Scholar, CORE, Unpaywall, SSRN, arXiv
lookup, DOI resolver, title search, full-text lookup, and external PDF extraction
were not called while `METADATA_LOOKUP_ENABLED=false`. The enabled/default backend
regression suite also passed: 138 tests.
