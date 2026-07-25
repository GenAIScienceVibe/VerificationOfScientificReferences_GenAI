# BE-10 Integration Note

This backend now includes BE-10 — GenAI Verification Orchestration.

Preserved baselines:

- BE4.2 DOI attachment/reference quality
- BE-5 DOI metadata lookup
- BE-6 claim/citation management
- BE-7 evidence package builder
- BE-8 verification cache layer
- BE-9 RAG/ML integration

New BE-10 pieces:

- `app/services/genai_verification.py`
- `app/services/verification_orchestrator.py`
- `app/api/v1/verification.py`
- `tests/test_be10_verification_orchestration.py`
- `scripts/validate_uploaded_pdfs_be10.py`

BE-10 uses mockable GenAI verification by default and does not call live Groq in tests.
