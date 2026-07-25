# Merge Resolution Report — `rag/api.py` upstream merge

**Date:** 2026-06-29  
**Role:** Merge Conflict Resolution Agent  
**Conflict file:** `rag/api.py`  
**Result:** PASS  
**Commit created:** No

## Conflict resolved

The only unmerged file, `rag/api.py`, was resolved manually and staged as resolved. No whole-file “ours” or “theirs” selection was used. All conflict markers were removed, and `git diff --name-only --diff-filter=U` returns no files.

## Root cause

Local INT-QA work and upstream commit `f0e61be` changed the same two Door 1 regions:

- the module-level source-embedding cache declaration; and
- the preprocessing/cache-key construction inside `retrieve_evidence()`.

The upstream branch added Door 2 retry behavior and changed the older cache key to `reference_id:doi`. The validated local branch had already replaced that cache with the stronger INT-QA-014 key. That local key binds normalized DOI, reference ID, source URL, evidence availability, and a SHA-256 fingerprint of source text. Taking either side wholesale would therefore have discarded either a legitimate upstream retry improvement or validated cache isolation.

## Manual merge decisions

1. Kept the local `_EmbeddingCacheKey` dataclass and `_build_embedding_cache_key()` implementation instead of the upstream `reference_id:doi` string key.
2. Kept local evidence preprocessing and its safe failure response before cache-key construction.
3. Added the upstream `_LLM_MAX_ATTEMPTS = 2` constant.
4. Kept the upstream `verify_claim()` retry loop for empty responses and transient LLM exceptions.
5. Left all already auto-merged upstream files untouched.

## Upstream behavior preserved

- Door 2 now makes at most two `generate_verdict()` attempts and retries empty or exception-producing calls.
- Existing public `retrieve_evidence()` and `verify_claim()` signatures remain unchanged.
- The separately auto-merged BE14 notes/onboarding, metadata lookup, safety-policy, text-processing, and verifier-prompt changes remain staged without resolution-agent edits.

## Local INT-QA behavior preserved

- **INT-QA-003:** DOI status safety remains intact; non-`VALID` statuses are not promoted to valid behavior.
- **INT-QA-004:** requested Door 1 `top_k` remains bounded and honored, with safe defaults and normalized 0–1 scores.
- **INT-QA-009:** chunk provenance retains safe `source`/`source_url` support without exposing local paths.
- **INT-QA-010:** safe Door 1 failure messages and backend validation/persistence sanitization remain covered by passing focused tests.
- **INT-QA-013:** the backend-facing unmatched `semantic_cache_match` default remains available.
- **INT-QA-014:** the cache key retains normalized DOI, reference/source identity, source URL, evidence availability, and source-text fingerprint; cross-DOI or changed-source reuse is prevented.
- **INT-QA-008:** `rag.api.retrieve_evidence` remains a module-level monkeypatch target for the deterministic real-adapter validator; no live embedding provider or API key was needed.

## Files changed by this resolution

- `rag/api.py` — conflict resolved and staged.
- `qa/reports/MERGE_RESOLUTION_REPORT_RAG_API_UPSTREAM_F0E61BE.md` — this report created.

No other production, test, or script file was edited by the resolution agent.

## Validation

| Command | Result |
|---|---|
| `backend/.venv/bin/python -m py_compile rag/api.py` | PASS |
| `backend/.venv/bin/python -m pytest tests/rag/test_api.py -q --tb=short` | PASS — 28 passed |
| `backend/.venv/bin/python -m pytest tests/rag -q --tb=short` | PASS — 365 passed |
| `cd backend && .venv/bin/python -m compileall app scripts` | PASS |
| `cd backend && .venv/bin/pytest -q tests/unit/test_group2_rag_contract_safety.py tests/unit/test_real_rag_pdf_validation_mode.py tests/test_be9_rag_ml_integration.py --tb=short` | PASS — 72 passed |
| `cd backend && .venv/bin/python scripts/run_integrated_rag_checks.py` | PASS — 233 backend tests, OpenAPI/check/demo, real RAG import, and 365 RAG tests; `INTEGRATED_VALIDATION_RESULT=PASS` |
| `git diff --check` | PASS — no whitespace errors |
| conflict-marker scan of `rag/api.py` | PASS — no markers found |
| `git diff --name-only --diff-filter=U` | PASS — empty; no unmerged files |

## Remaining risks

- Validation was deterministic and offline; it did not exercise a live external LLM/provider response.
- Other auto-merged upstream files are outside this conflict-only resolution scope. They passed the integrated regression suite but were not changed or independently accepted by this report.
- The upstream Door 2 API retry now surrounds verifier-layer empty-response retry behavior, so live-provider call volume should remain observable in deployment.

## Readiness

**Ready to commit merge: Yes.** The conflict is staged as resolved, there are no unmerged files, and all requested validation passed. No commit was created.
