# BE-4.2 Validation Report

## Commands executed

```bash
python -m compileall app
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
pytest -q
python scripts/qa_real_pdf_api_test.py /mnt/data/Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf /mnt/data/SeminarPaper_20.01..pdf
```

## Results

| Check | Result |
|---|---:|
| Python compileall | PASSED |
| FastAPI import/OpenAPI | PASSED |
| OpenAPI path count | 11 |
| Database initialization | PASSED |
| Database table count | 18 |
| Pytest | 48 passed |
| Real PDF API QA | PASSED for both PDFs |

## Real PDF manual QA summary

| PDF | References | DOI FOUND | DOI MISSING | DOI MALFORMED | Source DOI count | Extracted DOI count | DOI coverage | QA pass |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf | 24 | 21 | 3 | 0 | 21 | 21 | 1.0 | Yes |
| SeminarPaper_20.01..pdf | 37 | 21 | 16 | 0 | 21 | 21 | 1.0 | Yes |

## Critical regression checks passed

- `10.1146/annurev-psych-120710-100452` is recovered.
- `10.1146/annurev-psych-120710-preacher` is not produced.
- DOI-only and DOI URL lines are not created as standalone references.
- Journal continuation fragments are attached to previous references.
- No survey/appendix leak markers appear as references.
- No bad `FOUND` DOI values end with `-`.
- Invalid `doi_status=BAD_STATUS` is rejected with HTTP 422.

## Known remaining limitation

BE-4.2 is deterministic reference/DOI extraction only. Some non-DOI references remain `MISSING`, which is expected and should be handled by BE-5/BE-6 as not directly resolvable by DOI unless later metadata search by title is intentionally added. BE-4.2 does not invent DOI values and does not call external metadata services.
