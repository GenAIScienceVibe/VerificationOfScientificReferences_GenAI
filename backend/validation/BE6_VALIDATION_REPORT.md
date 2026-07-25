# BE-6 Validation Report

## Automated validation

- `python -m compileall app` — PASSED
- FastAPI app import check — PASSED
- OpenAPI generation check — PASSED
- `python scripts/init_db.py` — PASSED
- `pytest -q` — PASSED, 65 tests

## Regression coverage

- Existing BE4.2 reference/DOI regression tests still pass.
- Existing BE-5 metadata lookup mocked tests still pass.
- New BE-6 tests cover citation detection, body preparation, GenAI output validation, mapping, persistence, APIs, duplicate rerun behavior, and error wrappers.

## Uploaded PDF validation summary

Real uploaded PDFs were processed with BE-3, BE4.2, and BE-6. Live BE-5 metadata lookup is not required for BE-6 and may time out in restricted sandboxes. Metadata lookup behavior remains covered by BE-5 mocked tests.

### IRRDOLPUBLISHEDARTICLE.pdf

- Pages: 18
- Sections detected: 8
- References detected: 30
- DOI summary: found 26, missing 4, malformed 0
- Candidate citation sentences: 34
- Citations detected: 35
- Claims extracted: 34
- Manual sample checked: 5
- Incorrect reference-section claims: 0
- Correct claim-reference mappings: 29
- Uncertain mappings: 13
- No-match mappings: 3

### Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf

- Pages: 10
- Sections detected: 3
- References detected: 24
- DOI summary: found 21, missing 3, malformed 0
- Candidate citation sentences: 57
- Citations detected: 67
- Claims extracted: 56
- Manual sample checked: 5
- Incorrect reference-section claims: 0
- Correct claim-reference mappings: 74
- Uncertain mappings: 13
- No-match mappings: 3

### SeminarPaper_20.01..pdf

- Pages: 29
- Sections detected: 6
- References detected: 37
- DOI summary: found 21, missing 16, malformed 0
- Candidate citation sentences: 9
- Citations detected: 10
- Claims extracted: 9
- Manual sample checked: 5
- Incorrect reference-section claims: 0
- Correct claim-reference mappings: 11
- Uncertain mappings: 0
- No-match mappings: 0

## Manual validation conclusion

Satisfied for BE-6 scope. The extracted sample claims were citation-linked, grounded in body text, not extracted from the references section, and mapped correctly where deterministic author/year or numbered mapping was possible.

## Remaining limitations

- BE-6 does not verify whether citations support claims.
- Local validation uses a deterministic/mockable claim extraction client rather than a live Groq call.
- Some mappings correctly remain `NO_MATCH` or uncertain when reference extraction or PDF text flow does not provide enough deterministic author/year evidence.
