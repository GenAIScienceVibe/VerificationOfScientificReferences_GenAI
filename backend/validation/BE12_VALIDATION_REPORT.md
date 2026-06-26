# BE-12 Validation Report

## Commands run

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be12.py
python -c "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python scripts/validate_uploaded_pdfs_be12.py --reset-db /mnt/data/IRRDOLPUBLISHEDARTICLE.pdf /mnt/data/Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf /mnt/data/SeminarPaper_20.01..pdf
```

## Results

- Compile: PASSED
- FastAPI import/OpenAPI: PASSED
- OpenAPI path count: 44
- DB init: PASSED
- Pytest: 115 passed
- Uploaded-PDF validation: completed for 3 PDFs

## Uploaded-PDF validation summary

| PDF | Report generated | References | Verification results | Feedback API | Mapping feedback | UAT survey |
|---|---:|---:|---:|---:|---:|---:|
| IRRDOLPUBLISHEDARTICLE.pdf | Yes | 30 | 42 | Yes | Yes | Yes |
| Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf | Yes | 24 | 86 | Yes | Yes | Yes |
| SeminarPaper_20.01..pdf | Yes | 37 | 11 | Yes | Yes | Yes |

## Limitations

- Mock RAG and mock GenAI were used in validation because no real RAG/GenAI services were configured in the sandbox.
- HTML report is supported. PDF export is deferred to a future phase/enhancement.
- User feedback is stored and not automatically applied as truth.
