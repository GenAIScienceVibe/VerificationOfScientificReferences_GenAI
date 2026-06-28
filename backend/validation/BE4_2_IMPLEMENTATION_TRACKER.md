# BE-4.2 Implementation Tracker

| Task | Status | Evidence |
|---|---|---|
| Baseline BE-4.1 validation completed | Done | BE-4.1 defects confirmed: low DOI extraction despite DOI values in source references |
| DOI inventory utility implemented | Done | `extract_doi_inventory`, `build_doi_coverage_report` |
| DOI normalization improved | Done | prefix removal, trailing punctuation cleanup, unsafe suffix rejection |
| Safe DOI line continuation implemented | Done | refuses author-start continuations; numeric/lowercase DOI suffixes repaired |
| DOI-only line attachment implemented | Done | unit test covers DOI URL line after previous reference |
| URL-only DOI attachment implemented | Done | DOI URL continuations retained, not dropped as noise |
| Reference start scoring improved | Done | stricter year-before-DOI author-year checks |
| Journal continuation merge implemented | Done | Frontiers/Organizational/Psychology continuation tests and manual PDF validation |
| Final DOI re-scan implemented | Done | DOI extraction happens after final reference merge |
| DOI coverage report implemented | Done | extraction response contains `doi_coverage` |
| Quality warnings added | Done | low coverage warning supported |
| QA script updated | Done | reports coverage, marker refs, bad DOI endings, standalone DOI refs, pass/fail |
| PDF1 real-PDF fixture added | Done | `pdf1_be42_reference_section.txt`, `pdf1_expected_dois.txt` |
| PDF2 real-PDF fixture added | Done | `pdf2_be42_reference_section.txt`, `pdf2_expected_dois.txt` |
| Unit tests added | Done | `test_be4_2_doi_attachment.py` |
| Integration/regression tests added | Done | `test_be4_2_real_pdf_regression.py` |
| Real-PDF API QA script run | Done | `validation/be4_2_real_pdf_api_results.json` |
| compileall passed | Done | `python -m compileall app` |
| pytest passed | Done | 48 passed |
| DB init passed | Done | 18 tables |
| OpenAPI generation passed | Done | 11 paths |
| Validation report written | Done | `BE4_2_VALIDATION_REPORT.md` |
| Final ZIP packaged | Done | `VerificationOfScientificReferences_GenAI_BE4_2_DOI_Attachment_Reference_Quality.zip` |
