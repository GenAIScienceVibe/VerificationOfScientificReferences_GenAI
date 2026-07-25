# Initial Integrated Backend + RAG/ML QA Findings

These findings were identified from the first review of the latest merged backend + RAG/ML package. They should be used as the initial task list for Development/Fixing/QA agents.

## INT-QA-001 — Real RAG cannot import/run because dependencies are missing

Severity: P1  
Status: Open  
Blocking: Yes  
Component: RAG / Backend runtime  

Problem: Backend real RAG paths import `rag.api`, but backend runtime does not include all RAG dependencies. Previous import/test attempts failed with missing modules such as `tiktoken`, `openai`, `rank_bm25`, and `flashrank`.

Expected: Real RAG import and RAG unit tests run successfully in the documented integration environment.

Required fix: Provide a clear dependency setup strategy: separate RAG service environment or combined integrated requirements. Validate `from rag.api import retrieve_evidence, verify_claim` and backend `RagDirectClient` import.

## INT-QA-002 — Metadata disabled mode still risks external title lookup calls

Severity: P1  
Status: Open  
Blocking: Yes  
Component: DOI metadata lookup  

Problem: Title-based DOI fallback can run before honoring `METADATA_LOOKUP_ENABLED=false`. This can trigger CrossRef/OpenAlex/Semantic Scholar/CORE/Unpaywall-style calls in offline/mock validation mode.

Expected: If `METADATA_LOOKUP_ENABLED=false`, no external metadata/title/full-text lookup should run.

Required fix: Move metadata disabled guard before every external metadata/title/full-text fallback call. Add regression tests.

## INT-QA-003 — Backend FOUND DOI maps to RAG VALID unsafely

Severity: P1  
Status: Open  
Blocking: Yes  
Component: RAG integration / DOI safety  

Problem: Backend `DoiStatus.FOUND` means extracted but not metadata-verified. Mapping it to RAG `VALID` is academically unsafe.

Expected: Only backend `VALID` maps to RAG `VALID`. `FOUND`, `LOOKUP_FAILED`, `MISSING`, and `MALFORMED` should fail safely or map to unresolvable/invalid according to safety policy.

Required fix: Update mapping in `RagDirectClient` and any real GenAI/RAG verifier path. Add tests.

## INT-QA-004 — Real RAG ignores backend top_k

Severity: P1/P2  
Status: Open  
Blocking: Yes for contract acceptance  
Component: RAG retrieval contract  

Problem: Backend request includes `retrieval_options.top_k`, but real RAG uses fixed `DOOR1_TOP_K = 5` or returns a fixed number of chunks.

Expected: Real RAG must respect backend top_k or adapter must truncate returned chunks to requested top_k.

Required fix: Add top_k to RAG request model or enforce in backend adapter. Add tests for top_k=1/3/5.

## INT-QA-005 — Direct Python RAG import replaces service boundary

Severity: P2/P1 depending final architecture decision  
Status: Open  
Blocking: No if explicitly accepted for demo; Yes if service boundary is mandatory  
Component: Architecture  

Problem: Integration uses direct Python imports (`rag.api`) instead of HTTP service endpoint `/internal/rag/retrieve-evidence`.

Expected: Either implement an HTTP adapter service or clearly document direct in-process RAG as the accepted demo integration approach and its risks.

Required fix: Architecture decision required. If direct import remains, document it and validate dependency/runtime isolation. If HTTP service is required, implement adapter.

## INT-QA-006 — RAG tests are not included in backend validation and fail initially

Severity: P1  
Status: Open  
Blocking: Yes  
Component: Tests / QA  

Problem: Backend pytest passes, but root RAG tests were not included and previously failed during collection due missing dependencies.

Expected: Integrated validation should include backend tests and RAG tests, or document separate commands for both. RAG tests must pass in the integration environment.

Required fix: Add integrated validation command/script and resolve dependencies.

## INT-QA-007 — Full-text/source-PDF/Unpaywall/arXiv/CORE pipeline lacks end-to-end validation

Severity: P2  
Status: Open  
Blocking: No for first real RAG retrieval if abstract-only path works; Yes before claiming full-text pipeline complete  
Component: BE14/full-text  

Problem: Code exists for user source-PDF upload, Unpaywall/arXiv/CORE/full-text paths, but end-to-end validation is not proven.

Expected: Tests prove source PDF upload extracts text, stores it safely, updates evidence availability, and allows RAG retrieval from full text.

Required fix: Add endpoint tests and real/fixture validation.
