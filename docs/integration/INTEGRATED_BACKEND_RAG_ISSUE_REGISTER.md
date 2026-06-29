# Integrated Backend + RAG/ML Issue Register

This register summarizes the current issues to resolve before the merged Backend + RAG/ML package can be accepted as a true live integration. It is based on the latest integrated package review.

## Current verdict

Backend mock-mode validation remains strong, but live RAG/ML integration is not yet accepted. The package is ready for a focused Codex QA/fixing cycle, not final integrated release.

## P1 blockers

### INT-QA-001 — Real RAG dependency/runtime readiness
Real RAG cannot be treated as integrated until dependencies are installable and imports pass from the backend runtime.

Required evidence:
```bash
python -c "from rag.api import retrieve_evidence, verify_claim; print('ok')"
RAG_MOCK_MODE=false GENAI_MOCK_MODE=true python -c "from app.services.rag_ml_integration import RagDirectClient; print('ok')"
pytest tests/rag -q
```

### INT-QA-002 — Metadata-disabled guard
When `METADATA_LOOKUP_ENABLED=false`, no external metadata/title/full-text lookup should occur. This includes DOI title search fallbacks and providers such as CrossRef, OpenAlex, Semantic Scholar, CORE, Unpaywall, and arXiv.

### INT-QA-003 — Unsafe DOI status mapping
Only backend DOI status `VALID` should become real RAG `VALID`. `FOUND` is extracted but unverified and must not be treated as validated.

Recommended mapping:
| Backend DOI status | RAG-side status/action |
|---|---|
| VALID | VALID |
| INVALID | INVALID |
| MALFORMED | INVALID or UNRESOLVABLE |
| MISSING | UNRESOLVABLE / no evidence |
| LOOKUP_FAILED | UNRESOLVABLE / no evidence |
| FOUND | UNRESOLVABLE unless explicit policy allows unverified retrieval |

### INT-QA-004 — Real RAG top_k compliance
Backend `retrieval_options.top_k` must be respected. If RAG library cannot accept top_k, the backend adapter must truncate returned chunks safely.

### INT-QA-006 — RAG tests in integrated validation
Backend tests passing is not enough. RAG tests must pass too, and a combined validation path must exist.

## P2 issues

### INT-QA-005 — Service boundary decision
The current merge uses direct Python imports. This may be acceptable for demo but must be documented. If the architecture requires a service boundary, implement a RAG HTTP adapter with:
- GET /health
- GET /health/readiness
- POST /internal/rag/retrieve-evidence

### INT-QA-007 — Full-text/source-PDF validation
Full-text/source PDF logic needs end-to-end tests proving:
- source PDF upload extracts source text
- source text is stored safely
- evidence package becomes FULL_TEXT_AVAILABLE or PREPRINT_AVAILABLE when appropriate
- real RAG retrieves from uploaded source text

## Additional validation concerns

- Real RAG scores must always be 0–1.
- Real RAG chunks should include source and source_url where available.
- Real RAG failures should include structured error details.
- Real GenAI/Door 2 should not be enabled before Door 1 retrieval is accepted.
- Mock mode must remain available and clearly labelled.
- Private PDFs, `.env`, DB files, `.git`, IDE files, and caches should not be shared publicly.

## Acceptance gates

The integration can be accepted only after:
- No P1 findings remain open.
- Backend tests pass.
- RAG tests pass.
- OpenAPI validation passes.
- Real RAG import passes.
- Real RAG + mock GenAI pipeline passes.
- Real-PDF validation passes in the staged real-RAG mode.
- No unsupported support labels are returned.
- No unsafe DOI mapping remains.
- BE11 safety still applies.
