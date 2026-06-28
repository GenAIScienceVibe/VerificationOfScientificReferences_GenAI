# BE-11 Integration Note

BE-11 adds the deterministic backend safety/confidence policy layer on top of BE-10.

## Preserved baseline
This package keeps the prior phases intact:

- BE4.2 DOI Attachment + Reference Quality
- BE-5 DOI Metadata Lookup
- BE-6 Claim and Citation Management
- BE-7 Evidence Package Builder
- BE-8 Verification Cache Layer
- BE-9 RAG/ML Integration
- BE-10 GenAI Verification Orchestration

## Main additions

- `app/services/safety_policy.py`
- safety endpoints in `app/api/v1/verification.py`
- BE-11 tests in `tests/test_be11_safety_confidence.py`
- uploaded-PDF validation script `scripts/validate_uploaded_pdfs_be11.py`

## Important boundary
BE-11 does not implement BE-12 report generation or BE-13 demo hardening.
