# QA Open Findings Status — After Group 2

Run date: 2026-06-28 (Asia/Singapore)  
Role: QA Documentation Agent  
Repository: `/home/shalith/Downloads/VerificationOfScientificReferences_GenAI_Codex_Agent_Ready/VerificationOfScientificReferences_GenAI`

## Current summary

- Total INT-QA finding files: **14**.
- Closed findings: **9**.
- Open non-blocking findings: **2**.
- Open blocking findings: **3**.
- Final integrated release: **BLOCKED** by INT-QA-007, INT-QA-008, and
  INT-QA-011.

This report preserves each finding file's literal `Blocking` value and
separately evaluates current release impact. INT-QA-001, INT-QA-002, and
INT-QA-006 are closed but still contain the historical field `Blocking: Yes`.
They do not currently block release because their status and closure notes show
independent resolution; the metadata inconsistency is reported without editing
the finding files.

## All INT-QA findings

| ID | Title | Severity | Status | Blocking value | Short problem summary | Disposition | Blocks final integrated release? |
|---|---|---|---|---|---|---|---|
| INT-QA-001 | Real RAG cannot import or collect its tests in the backend runtime | P1 | Closed | Yes | The backend runtime lacked the combined RAG dependencies, preventing real RAG imports and RAG test collection. | Closed | No — independently resolved; literal blocking field is stale. |
| INT-QA-002 | Title-based metadata providers are called while metadata lookup is disabled | P1 | Closed | Yes | Disabled metadata mode did not guard title lookup and could still call external metadata/full-text providers. | Closed | No — independently resolved; literal blocking field is stale. |
| INT-QA-003 | Backend FOUND DOI status maps to RAG VALID | P1 | Closed | No / Resolved | Extracted but unverified `FOUND` DOI status was incorrectly promoted to RAG `VALID`. | Closed | No. |
| INT-QA-004 | Real RAG ignores backend retrieval `top_k` | P1 | Closed | No / Resolved | The direct adapter and Door 1 used a fixed result count instead of propagating and enforcing backend `top_k`. | Closed | No. |
| INT-QA-005 | Direct Python RAG integration is undocumented and bypasses configured HTTP boundary | P2 | Open | No | Runtime uses in-process `rag.api` while HTTP service settings and documentation imply a different deployment boundary. | Still open | No — currently non-blocking, but the accepted deployment design remains unclear. |
| INT-QA-006 | Backend validation does not execute the root RAG test suite | P1 | Closed | Yes | Backend-only validation could pass without collecting or executing any root RAG tests. | Closed | No — independently resolved; literal blocking field is stale. |
| INT-QA-007 | Full-text upload, Unpaywall, arXiv, CORE, and RAG flow lacks end-to-end coverage | P2 | Open | Yes | No end-to-end test proves uploaded/provider full text reaches a full-text evidence package and real RAG retrieval. | Still open | **Yes.** |
| INT-QA-008 | No staged real-RAG + mock-GenAI PDF validation mode exists | P1 | Open | Yes | The PDF validator cannot explicitly run real RAG with mock GenAI and still forces/labels mock retrieval. | Still open | **Yes.** |
| INT-QA-009 | Real RAG drops source and source_url from returned chunks | P2 | Closed | No / Resolved | Real Door 1 results previously lost source identity and URL, preventing auditable persisted provenance. | Closed | No. |
| INT-QA-010 | Real RAG failures lose structured cause details | P2 | Closed | No / Resolved | Real RAG failures previously lost safe cause detail or could persist unsafe traceback/path/token content. | Closed | No. |
| INT-QA-011 | Private PDFs, runtime databases, and uploaded PDFs are tracked in the repository | P1 | Open | Yes | The repository tracks private PDF fixtures, populated databases, and uploaded artifacts, creating a privacy and packaging risk. | Still open | **Yes.** |
| INT-QA-012 | README and environment setup do not document the merged runtime accurately | P2 | Open | No | Integrated installation, working-directory, dependency, service-boundary, and mock/real validation instructions remain incomplete or stale. | Still open | No — currently non-blocking. |
| INT-QA-013 | Real RAG path does not provide the required semantic_cache_match default | P2 | Closed | No / Resolved | Real, failed, and skipped paths previously omitted the stable unmatched semantic-cache object. | Closed | No. |
| INT-QA-014 | RAG source embedding cache reuses across different DOIs | P1 | Closed | No / Resolved | Source embeddings could be reused across different DOI values, risking cross-source evidence contamination. | Closed | No. |

## Closed findings

- INT-QA-001 — Real RAG dependency and import readiness.
- INT-QA-002 — Metadata-disabled external call blocker.
- INT-QA-003 — Unsafe DOI status mapping.
- INT-QA-004 — Real RAG `top_k` handling.
- INT-QA-006 — RAG tests included in integrated validation.
- INT-QA-009 — RAG chunk traceability.
- INT-QA-010 — Real RAG failure-detail sanitization.
- INT-QA-013 — Semantic-cache default.
- INT-QA-014 — Cross-DOI RAG embedding-cache isolation.

## Open non-blocking findings

| Finding | File | Current impact |
|---|---|---|
| INT-QA-005 | `qa/findings/INT-QA-005_DIRECT_PYTHON_RAG_SERVICE_BOUNDARY.md` | Deployment boundary and misleading HTTP configuration remain unresolved, but the file marks this non-blocking. |
| INT-QA-012 | `qa/findings/INT-QA-012_INTEGRATED_DOCUMENTATION_GAP.md` | Integrated setup and mode documentation remain incomplete, but the file marks this non-blocking. |

## Open blocking findings

| Finding | Exact file name | Release-blocking reason |
|---|---|---|
| INT-QA-007 | `qa/findings/INT-QA-007_FULL_TEXT_PIPELINE_VALIDATION_GAP.md` | Full-text/provider-to-evidence-to-real-RAG behavior lacks end-to-end acceptance coverage. |
| INT-QA-008 | `qa/findings/INT-QA-008_REAL_RAG_VALIDATION_MODE.md` | Staged real-RAG + mock-GenAI PDF validation is unavailable, so live retrieval acceptance cannot be demonstrated. |
| INT-QA-011 | `qa/findings/INT-QA-011_PRIVATE_ARTIFACT_PACKAGING_RISK.md` | Private/tracked artifacts create an unresolved privacy and shareable-package approval risk. |

## Recommended next fixing group

**Group 3 — Final release blockers: INT-QA-007, INT-QA-008, and INT-QA-011.**

Recommended sequence:

1. Address INT-QA-011 first as a data-governance gate. Confirm ownership and
   approval before removing or replacing private artifacts; use approved
   synthetic/sanitized fixtures and verify the packaged archive.
2. Address INT-QA-007 by adding isolated full-text upload/provider tests and an
   end-to-end uploaded-PDF → evidence-package → real-RAG retrieval path.
3. Address INT-QA-008 using the approved fixtures from INT-QA-007 to add and
   run an explicitly labeled real-RAG + mock-GenAI PDF validation mode.

After the three blockers close, a documentation/boundary group can address
INT-QA-005 and INT-QA-012 together so the documented deployment and validation
instructions match the accepted runtime.

## Current release decision

**Do not approve the final integrated release.** Three blocking findings remain
open: INT-QA-007, INT-QA-008, and INT-QA-011.
