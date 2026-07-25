
# BE-12 — Report Generation and Feedback

BE-12 adds backend-generated verification reports and feedback/UAT storage on top of the BE4.2 + BE-5 + BE-6 + BE-7 + BE-8 + BE-9 + BE-10 + BE-11 baseline.

## Purpose

The backend now turns stored verification data into user-facing report content. The frontend can display the report, but the frontend does not calculate the verification summary itself.

## New endpoints

```text
GET  /api/v1/documents/{document_id}/summary
POST /api/v1/documents/{document_id}/reports
GET  /api/v1/reports/{report_id}
GET  /api/v1/documents/{document_id}/report
GET  /api/v1/reports/{report_id}/download?format=HTML
POST /api/v1/verification-results/{result_id}/feedback
POST /api/v1/claim-reference-links/{link_id}/feedback
POST /api/v1/uat/surveys
```

## Report sections

The HTML report includes:

1. Report header
2. Document overview
3. DOI/reference quality summary
4. Claim verification summary
5. High-risk / human-review claims
6. Detailed claim verification table
7. Evidence and safety notes
8. Limitations

## Summary calculation rules

The report and summary endpoint use backend-stored data only:

- `Document`
- `Reference`
- `SourceMetadata`
- `Claim`
- `Citation`
- `ClaimReferenceLink`
- `EvidencePackage`
- `RagRetrievalResult`
- `VerificationResult`
- `SafetyCheck`
- `Report`
- `UserFeedback`
- `UatSurvey`

BE-12 does not rerun verification and does not change final support labels.

## DOI summary

The DOI summary includes:

- total references
- valid DOIs
- missing DOIs
- malformed DOIs
- invalid DOIs
- metadata lookup succeeded
- metadata unavailable
- lookup failed
- average metadata match score when available

DOI metadata confirms source identity/availability; it does not prove that a claim is supported.

## Claim verification summary

The claim summary includes:

- supported
- partially supported
- not supported
- insufficient evidence
- needs human review
- average confidence
- cache-source counts
- evidence availability counts
- human-review count
- low-similarity count

Only final allowed support statuses are used.

## High-risk claim selection

A claim appears in the high-risk/human-review list if it has:

- `human_review_required = true`
- `support_status = NEEDS_HUMAN_REVIEW`
- `support_status = INSUFFICIENT_EVIDENCE`
- high-risk safety checks
- source unavailable
- low similarity
- missing/invalid/malformed DOI-related safety reasons

## Feedback behavior

Feedback is stored but is not automatically applied as truth.

Verification result feedback is linked to:

- `document_id`
- `result_id`
- optional `user_label`
- optional `user_comment`
- optional `user_role`

Claim-reference mapping feedback is linked to:

- `document_id`
- `link_id`
- optional `suggested_reference_id`
- optional `user_comment`
- optional `user_role`

Suggested references must belong to the same document.

## UAT survey behavior

The UAT endpoint stores ratings from 1 to 5:

- ease of use
- result clarity
- trust
- usefulness

The API does not require personal identifying data.

## PDF export behavior

BE-12 implements HTML report generation as the MVP. PDF export is intentionally not implemented because it would introduce extra rendering dependencies. `GET /reports/{report_id}/download?format=PDF` returns `REPORT_EXPORT_NOT_SUPPORTED`.

## Uploaded research-paper validation

Validation used the three uploaded PDFs through BE-3 to BE-12 with mock RAG/GenAI:

| PDF | Report generated | References | Verification results | Feedback tested | UAT tested |
|---|---:|---:|---:|---:|---:|
| IRRDOLPUBLISHEDARTICLE.pdf | Yes | 30 | 42 | Yes | Yes |
| Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf | Yes | 24 | 86 | Yes | Yes |
| SeminarPaper_20.01..pdf | Yes | 37 | 11 | Yes | Yes |

All reports included DOI summary, claim summary, high-risk list, detailed claim table, and limitations. No unsupported label such as `Hallucinated` was found.

## Validation commands

```bash
python -m compileall app scripts/validate_uploaded_pdfs_be12.py
python scripts/init_db.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python scripts/validate_uploaded_pdfs_be12.py --reset-db /path/to/paper1.pdf /path/to/paper2.pdf /path/to/paper3.pdf
```

## Limitations

- BE-12 generates reports from stored results; it does not rerun verification.
- BE-12 does not auto-apply feedback as truth.
- BE-12 does not replace human academic review.
- HTML is the MVP format; PDF export is a future enhancement.
- Mock RAG/GenAI validation proves backend behavior, not final AI quality.
