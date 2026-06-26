# BE-11 Validation Report

## Commands run

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be11.py
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python scripts/validate_uploaded_pdfs_be11.py --reset-db <three uploaded PDFs>
```

## Results

- Compile: PASSED
- FastAPI import/OpenAPI generation: PASSED
- OpenAPI path count: 36
- DB initialization: PASSED
- Database table count: 18
- Pytest: 107 passed
- Uploaded PDF validation: completed for all three uploaded PDFs

## Notes

Validation used mock RAG and mock GenAI because no real services were configured in the sandbox. BE-11 deterministic safety rules were applied to the produced verification results.

## Uploaded PDF validation summary

### IRRDOLPUBLISHEDARTICLE.pdf

- References detected: 30
- DOI summary: found 26, missing 4, malformed 0
- Claims extracted: 34
- Evidence packages created: 42
- Verification results produced: 42
- Human review flags: 41
- Confidence caps applied: 41
- Safety checks stored: 49
- High risk results: 4
- Medium risk results: 37
- Unsupported labels: none

### Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf

- References detected: 24
- DOI summary: found 21, missing 3, malformed 0
- Claims extracted: 56
- Evidence packages created: 87
- Verification results produced: 86
- Human review flags: 85
- Confidence caps applied: 85
- Safety checks stored: 101
- High risk results: 8
- Medium risk results: 77
- Unsupported labels: none

### SeminarPaper_20.01..pdf

- References detected: 37
- DOI summary: found 21, missing 16, malformed 0
- Claims extracted: 9
- Evidence packages created: 11
- Verification results produced: 11
- Human review flags: 10
- Confidence caps applied: 10
- Safety checks stored: 14
- High risk results: 2
- Medium risk results: 8
- Unsupported labels: none
