# BE-5 Validation Report - DOI Metadata Lookup

## Automated validation

| Command | Result |
|---|---:|
| `python -m compileall app` | PASSED |
| FastAPI app import check | PASSED |
| OpenAPI generation check | PASSED |
| OpenAPI path count | 14 |
| `python scripts/init_db.py` | PASSED |
| DB table count | 18 |
| `pytest -q` | 59 passed |

## BE4.2 regression protection

BE4.2 regression tests remain in the suite and passed. Covered areas include reference splitting, DOI extraction, DOI attachment, multiline references, malformed/missing DOI behavior, and real-PDF DOI coverage fixtures.

A BE-5 validation issue was found on `IRRDOLPUBLISHEDARTICLE.pdf`: the PDF text layer exposed a trailing DOI-only line without the corresponding author/title line. A defensive BE4.2-compatible improvement now preserves standalone DOI-only tails as orphan DOI-only references instead of attaching them to the previous reference. This prevents BE-5 metadata lookup from validating a DOI against the wrong reference entry.

## Uploaded research paper validation

The following PDFs were processed through BE-3 upload/text extraction, BE4.2 reference/DOI extraction, and BE-5 metadata lookup API behavior.

| PDF | Pages | Sections | References detected | DOI found | DOI missing | Malformed DOI | DOI coverage | Live metadata sample |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `IRRDOLPUBLISHEDARTICLE.pdf` | 18 | 8 | 30 | 26 | 4 | 0 | 1.0 | LOOKUP_FAILED due sandbox DNS/network restriction |
| `Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf` | 10 | 3 | 24 | 21 | 3 | 0 | 1.0 | LOOKUP_FAILED due sandbox DNS/network restriction |
| `SeminarPaper_20.01..pdf` | 29 | 6 | 37 | 21 | 16 | 0 | 1.0 | LOOKUP_FAILED due sandbox DNS/network restriction |

## Manual validation observations

### IRRDOLPUBLISHEDARTICLE.pdf

- Upload and text extraction succeeded.
- References section was detected from BE-3 sections.
- 30 reference rows were created after the orphan DOI-tail fix.
- DOI extraction coverage reached 26/26 DOIs found in the source reference section.
- Manual samples: Andrade correctly marked missing DOI; Chen DOI normalized to `10.1109/icalt52272.2021.00079`; Chiu DOI normalized to `10.1080/10494820.2023.2172044`; Crompton DOI normalized to `10.1186/s41239-023-00392-8`.
- Remaining limitation: one DOI-only tail was preserved as an orphan DOI-only reference because the PDF text layer did not expose the full Zhao reference text to the backend extraction layer.

### Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf

- Upload and text extraction succeeded.
- References were detected and split.
- 24 references were created.
- DOI extraction coverage reached 21/21 DOIs found in the source reference section.
- Manual samples: Afif correctly marked missing DOI; Akhyar DOI normalized to `10.32938/jitu.v3i1.3953`; Bhaskar DOI normalized to `10.1108/ijilt-11-2023-0220`; Dwivedi DOI extracted from the long reference entry.
- Remaining limitation: a final no-DOI reference after Supianto is appended in the raw reference text because the PDF source has weak separation near the end; no DOI was falsely assigned to it.

### SeminarPaper_20.01..pdf

- Upload and text extraction succeeded.
- References were detected and split.
- 37 references were created.
- DOI extraction coverage reached 21/21 DOIs found in the source reference section.
- Manual samples: Bauer DOI normalized to `10.1177/01492063241277168`; Bucher DOI normalized to `10.48550/arxiv.2405.15561`; Cheikh-Ammar DOI normalized to `10.4018/ijkm.336278`; Cohen book correctly marked missing DOI.
- Remaining limitation: some no-DOI sources and web-only sources remain missing DOI, which is expected.

## Metadata lookup validation limitation

The runtime sandbox cannot resolve external DNS (`Temporary failure in name resolution`). Therefore live CrossRef metadata lookup could not be completed in this environment. The BE-5 API handled that safely by returning HTTP 200 with per-reference `metadata_status=LOOKUP_FAILED`, storing a `SourceMetadata` failure row, preserving the normalized DOI and resolver URL, and not crashing the backend.

Official metadata success paths are validated with mocked CrossRef responses in unit/API tests, including metadata persistence, status updates, metadata scoring, 404 handling, timeout handling, malformed/missing DOI handling, and metadata cache reuse.

## Manual validation conclusion

Partially satisfied.

- Satisfied: automated tests, BE4.2 regression tests, PDF upload/text extraction, reference detection, DOI extraction, DOI normalization, DOI-to-reference attachment protection, safe failure handling, database persistence.
- Not fully satisfied in sandbox: live official CrossRef metadata retrieval and real metadata match scores for uploaded PDFs, because the execution environment has no external DNS/network access.
