# BE-4.1 Implementation Tracker

| Work package | Status | Evidence |
|---|---|---|
| WP1 baseline validation | Done | compileall/pytest/OpenAPI/DB commands rerun |
| WP2 stronger text cleanup | Done | `text_processing.py` adds DOI repair and page artifact cleanup |
| WP3 section boundary hardening | Done | references stop before appendix/survey headings |
| WP4 BE-4 reference-section validation | Done | `reference_extraction.py` trims provided References section again |
| WP5 DOI continuation repair | Done | unit test covers line-broken DOI repair and malformed trailing DOI |
| WP6 reference splitting/false positive filtering | Done | APA, numbered, bracketed, multi-line, footer, URL-only, survey artifacts covered |
| WP7 query enum validation | Done | invalid `doi_status` returns 422 standard wrapper |
| WP8 raw-text protection | Done | `ENABLE_RAW_TEXT_DEBUG_ENDPOINT=false` default, service/API gating added |
| WP9 safer re-extraction | Done | re-extraction blocked when downstream `SourceMetadata` exists |
| WP10 failed PDF audit behavior | Done | corrupted PDF error includes failed `doc_...` id |
| WP11 real-PDF regression tests | Done | sanitized real-PDF text fixtures and QA script added |
| WP12 validation/package | Done | `38 passed`, real-PDF API flow executed, package created |

## Remaining known limitation

PDF 1 still returns many DOI-missing references because the source extracted text does not expose DOI strings for every reference after conservative cleanup. This is not an API failure, but BE-5 must treat `MISSING` DOI values as manual-review candidates instead of performing metadata lookup.
