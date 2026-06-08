# BE-4.2 — DOI Attachment, Reference Continuation, and Extraction Quality Hardening

BE-4.2 hardens BE-4 reference and DOI extraction after real-PDF testing showed that BE-4.1 was API-stable but still lost DOI values during reference splitting.

## Scope

Implemented:

- Safe DOI continuation repair.
- DOI-only and DOI URL line attachment to the previous reference.
- Journal/volume/page continuation attachment to the previous reference.
- Final DOI re-scan after reference merging.
- DOI inventory and coverage diagnostics.
- Quality warnings for low DOI coverage.
- Prevention of next-author contamination inside DOI values.
- Real-PDF regression fixtures and tests.
- Improved real-PDF QA script with pass/fail metrics.

Still deferred:

- BE-5 metadata lookup.
- CrossRef, OpenAlex, DOI Resolver, Semantic Scholar.
- Claim extraction.
- Citation-reference mapping.
- Evidence package building.
- RAG retrieval.
- GenAI verification.
- Report generation and feedback workflows.

## DOI continuation strategy

BE-4.2 repairs examples such as:

```text
10.1111/j.1467-
9280.2007.01882.x
```

into:

```text
10.1111/j.1467-9280.2007.01882.x
```

but refuses to join if the next line looks like a new author:

```text
10.1146/annurev-psych-120710-
Preacher, K. J. (2004)
```

This prevents bad DOI values such as:

```text
10.1146/annurev-psych-120710-preacher
```

## Reference continuation strategy

BE-4.2 appends these continuation patterns to the previous reference instead of creating false rows:

- DOI-only lines.
- `https://doi.org/...` lines.
- journal-title continuation lines such as `Organizational Psychology, 3, ...`.
- volume/issue/page fragments with DOI.

When uncertain, BE-4.2 generally prefers appending to the previous reference over creating a false standalone reference.

## DOI coverage diagnostics

The extraction response now includes:

```json
{
  "doi_coverage": {
    "source_doi_count": 21,
    "extracted_doi_count": 21,
    "matched_doi_count": 21,
    "missing_from_extracted": [],
    "unexpected_extracted": [],
    "coverage_ratio": 1.0
  },
  "quality_warnings": []
}
```

If source DOI count is at least 5 and coverage is below 0.85, BE-4.2 adds:

```text
LOW_DOI_COVERAGE
```

This does not call BE-5 and does not invent metadata.

## Real-PDF validation result

The QA script was run against the two uploaded real PDFs. Both passed BE-4.2 quality gates:

- no appendix/survey marker references
- no standalone DOI references
- no continuation-fragment references
- no bad `FOUND` DOI ending
- no author-contaminated DOI such as `-preacher`
- invalid `doi_status` filter rejected with HTTP 422
- DOI coverage ratio 1.0 for both PDFs

## How to run real-PDF QA

```bash
python scripts/qa_real_pdf_api_test.py /path/to/pdf1.pdf /path/to/pdf2.pdf
```

The script reports API status, reference counts, DOI coverage, bad markers, and pass/fail reasons.
