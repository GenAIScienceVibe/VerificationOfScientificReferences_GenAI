# Shared Context — Integrated Backend + RAG/ML Codex Work

## Project

verifAI / RefCheck AI: verifies scientific references by processing uploaded papers, extracting references/DOIs, looking up metadata, extracting citation-linked claims, building evidence packages, retrieving evidence through RAG/ML, orchestrating GenAI verification, applying safety rules, and generating reports/feedback/UAT outputs.

## Final architecture

Frontend → Backend → AI/ML/RAG → Backend → Frontend  
AI/ML/RAG → Backend → External Academic Sources

The backend remains the orchestrator and final safety authority.

## Previous stable baseline

The backend BE1–BE13 package passed final QA in mock RAG/GenAI mode:
- 128 automated tests passed.
- OpenAPI validation passed.
- Demo pipeline passed.
- Real-PDF validation passed for three PDFs.
- DOI-only reference issue QA-BE13-004 was fixed and revalidated.
- All QA findings QA-BE13-001 to QA-BE13-004 were closed.

## Latest integrated package status

The latest package has merged RAG/ML and backend code. It adds direct Python RAG integration and BE14-style source full-text features. It has not yet passed full live RAG/ML acceptance. Known issues are recorded in `docs/integration/INTEGRATED_BACKEND_RAG_ISSUE_REGISTER.md` and `qa/findings/INTEGRATED_QA_INITIAL_FINDINGS.md`.

## Important mode distinction

Mock mode:
- `RAG_MOCK_MODE=true`
- `GENAI_MOCK_MODE=true`
- validates backend orchestration, contracts, database flow, safety, and reports.

Live/real mode:
- `RAG_MOCK_MODE=false`
- `GENAI_MOCK_MODE=false` or `GENAI_MOCK_MODE=true` for staged testing
- requires RAG dependencies/API keys and must be separately validated.

Do not claim live RAG/GenAI is validated when only mock mode has passed.

## Immediate integrated package blockers

Treat these as the first Development Agent tasks:
1. INT-QA-001 — Real RAG cannot import/run because RAG dependencies are missing from backend runtime or not installed in a combined environment.
2. INT-QA-002 — Metadata-disabled mode can still trigger title-based DOI/external metadata fallback before honoring `METADATA_LOOKUP_ENABLED=false`.
3. INT-QA-003 — Backend `FOUND` DOI status maps to RAG `VALID`, which is academically unsafe.
4. INT-QA-004 — Real RAG ignores backend `top_k`.
5. INT-QA-005 — Direct Python import of RAG replaces the originally expected service boundary and must be documented or adapted safely.
6. INT-QA-006 — Root RAG tests are not included in backend validation and previously failed due missing dependencies.
7. INT-QA-007 — Full-text upload/Unpaywall/arXiv/CORE pipeline lacks end-to-end validation.

## Required acceptance before saying “integrated RAG is complete”

- Backend tests pass.
- RAG tests pass.
- Backend-RAG integration tests pass.
- Real RAG import works.
- `RAG_MOCK_MODE=false, GENAI_MOCK_MODE=true` pipeline passes.
- Scores are normalized to 0–1.
- Backend `top_k` is respected.
- No unsafe DOI status mapping.
- No external metadata calls when metadata lookup is disabled.
- Real-PDF validation passes in staged real-RAG mode.
- No unsupported support labels.
- BE11 safety rules still apply.
