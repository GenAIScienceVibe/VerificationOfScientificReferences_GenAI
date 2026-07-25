# BE-4 — Reference and DOI Extraction

BE-4 implements deterministic reference and DOI extraction on top of the BE-3 processed document text.

## Scope implemented

- Detect a references section from BE-3 `DocumentSection` records first.
- Fall back to `Document.cleaned_text` when no stored References section exists.
- Split individual references using rule-based patterns.
- Extract and normalize DOI values using regex.
- Store extracted references in the `references` table.
- Update `Document.references_count` and document status.
- Expose reference extraction and retrieval APIs.

## APIs

### POST `/api/v1/documents/{document_id}/extract-references`

Runs BE-4 extraction synchronously for the local/demo backend.

Response data includes:

```json
{
  "document_id": "doc_123",
  "references_count": 3,
  "doi_summary": {
    "found": 2,
    "missing": 1,
    "malformed": 0
  },
  "status": "REFERENCES_EXTRACTED"
}
```

### GET `/api/v1/documents/{document_id}/references`

Returns paginated references for a document.

Supported filters:

- `doi_status`
- `metadata_status`
- `page`
- `page_size`

Example:

```bash
curl "http://127.0.0.1:8000/api/v1/documents/doc_123/references?doi_status=FOUND&page=1&page_size=20"
```

### GET `/api/v1/references/{reference_id}`

Returns a single extracted reference.

## Reference section detection strategy

BE-4 searches in this order:

1. Stored `DocumentSection` named `References`, `Bibliography`, `Works Cited`, or `Reference List`.
2. Fallback scan in `Document.cleaned_text` for headings:
   - References
   - Bibliography
   - Works Cited
   - Reference List
   - Literatur
   - Literaturverzeichnis

When scanning full text, BE-4 prefers the last matching heading because references usually appear near the end.
It stops at likely post-reference headings such as Appendix, Appendices, Supplementary Material, Acknowledgements, or Acknowledgments.

## Supported reference formats

The deterministic splitter supports common cases:

- APA-like author-year references:
  - `Smith, J. (2023). Title...`
- Bracket-numbered references:
  - `[1] Smith, J. (2023). Title...`
- Numbered references:
  - `1. Smith, J. (2023). Title...`
  - `1) Smith, J. (2023). Title...`
- Blank-line separated references.
- Multi-line wrapped references.
- DOI-containing references where DOI is split across PDF line wrapping after BE-3 cleaning.

## DOI extraction and normalization

BE-4 uses this core DOI regex:

```text
10\.\d{4,9}/[-._;()/:A-Z0-9]+
```

Matching is case-insensitive.

Supported DOI input examples:

- `10.1234/ABC.Def.2023`
- `doi:10.1234/ABC.Def.2023`
- `DOI: 10.1234/ABC.Def.2023`
- `https://doi.org/10.1234/ABC.Def.2023`
- `http://dx.doi.org/10.1234/ABC.Def.2023`

Normalization behavior:

- removes `doi:` / `DOI:` prefixes
- removes `https://doi.org/` and `http://dx.doi.org/`
- strips obvious trailing sentence punctuation such as `.`, `,`, `;`
- strips unmatched trailing `)`
- lowercases the normalized DOI

Example:

```text
https://doi.org/10.1234/ABC.Def.2023.
```

becomes:

```text
10.1234/abc.def.2023
```

## DOI status meanings in BE-4

BE-4 does only syntax-level DOI extraction.

- `FOUND`: DOI-like value was extracted and passed syntax normalization.
- `MISSING`: no DOI was found in the reference.
- `MALFORMED`: DOI-like text or DOI prefix exists, but it cannot be normalized to the supported DOI syntax.

BE-4 does not use:

- `VALID`
- `INVALID`
- `LOOKUP_FAILED`

Those statuses belong to BE-5 DOI metadata/existence lookup.

## Idempotency

Re-running BE-4 for the same document replaces existing extracted references for that document. This avoids duplicate reference records during local/demo development.

## Limitations

BE-4 does not:

- verify whether a DOI exists
- call CrossRef, OpenAlex, Semantic Scholar, or DOI Resolver
- fetch official metadata
- extract claims
- map in-text citations to references
- build evidence packages
- call RAG services
- call GenAI services
- decide support status
- generate final reports

## Tests

Run:

```bash
pytest -q
```

BE-4 tests cover:

- reference section detection
- APA/numbered/bracketed reference splitting
- DOI extraction and normalization
- malformed/missing DOI behavior
- API extraction endpoint
- reference list endpoint and filters
- single reference endpoint
- idempotent re-run behavior
- standard error wrappers
