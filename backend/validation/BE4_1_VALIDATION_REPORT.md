# BE-4.1 Validation Report

## Commands run

```bash
python -m compileall app
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
pytest -q
python scripts/qa_real_pdf_api_test.py <pdf1> <pdf2>
```

## Results

| Check | Result |
|---|---:|
| compileall | PASSED |
| FastAPI import/OpenAPI | PASSED |
| OpenAPI path count | 11 |
| DB initialization | PASSED |
| DB table count | 18 |
| pytest | 38 passed |

## Real PDF API test summary

| PDF | Upload | Pages | Sections | References | DOI FOUND | DOI MISSING | DOI MALFORMED | Bad markers | Bad FOUND DOI endings |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf | 200 | 10 | 3 | 23 | 3 | 20 | 0 | 0 | 0 |
| SeminarPaper_20.01..pdf | 200 | 29 | 6 | 38 | 11 | 27 | 0 | 0 | 0 |

## Notes

- `/raw-text` is disabled by default and enabled only for local QA through `ENABLE_RAW_TEXT_DEBUG_ENDPOINT=true`.
- BE-4.1 does not call external metadata APIs, RAG, or GenAI.
- PDF 1 still has many DOI-missing references because several references in the extracted text do not expose DOI strings after conservative cleanup; this remains a quality limitation for BE-5 safeguards/manual review, not an API failure.
- Real-PDF regression checks confirm no Appendix/survey leakage in PDF 2 and no journalpedia/footer marker rows in the extracted reference list.
