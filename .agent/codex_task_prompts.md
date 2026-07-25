# Ready-to-Paste Codex Prompts — Integrated Backend + RAG/ML

## 1. Baseline QA prompt

```text
Read AGENTS.md, backend/AGENTS.md, rag/AGENTS.md, .agent/shared_integrated_context.md, .agent/qa_agent.md, docs/integration/INTEGRATED_BACKEND_RAG_ISSUE_REGISTER.md, and qa/findings/INTEGRATED_QA_INITIAL_FINDINGS.md.

Act as QA Agent.
Do not modify production code.

Run a full integrated Backend + RAG/ML QA baseline. Validate backend mock mode, RAG imports, RAG unit tests, backend-RAG contract compatibility, real-PDF validation, and full-text/source-PDF features where possible.

Save the report under qa/reports/QA_INTEGRATED_BASELINE_REPORT.md and create/update findings under qa/findings/.
Return final decision PASS / PASS WITH MINOR ISSUES / FAIL.
```

## 2. Development prompt for first blocker group

```text
Read AGENTS.md, backend/AGENTS.md, rag/AGENTS.md, .agent/shared_integrated_context.md, .agent/development_agent.md, docs/integration/INTEGRATED_BACKEND_RAG_ISSUE_REGISTER.md, and qa/findings/INTEGRATED_QA_INITIAL_FINDINGS.md.

Act as Development Agent.

Implement only these issues first:
- INT-QA-001: Real RAG cannot import/run due missing dependency/runtime setup.
- INT-QA-002: METADATA_LOOKUP_ENABLED=false must disable all metadata/title lookup/external calls.
- INT-QA-003: FOUND DOI status must not map to RAG VALID unsafely.
- INT-QA-004: Real RAG must respect backend top_k.
- INT-QA-006: RAG tests must be included in integrated validation.

Do not redesign unrelated code. Do not touch frontend. Preserve backend mock-mode tests and API contracts. Add regression tests. Return a Development Report only.
```

## 3. Fixing prompt

```text
Read AGENTS.md, .agent/shared_integrated_context.md, .agent/fixing_agent.md, latest QA report, and the assigned finding files.

Act as Fixing Agent.
Fix only these findings: [INSERT FINDING IDS].
Do not refactor unrelated modules. Do not weaken tests. Add regression tests for each fix. Return a Fixing Report only.
```

## 4. Re-validation prompt

```text
Read AGENTS.md, .agent/shared_integrated_context.md, .agent/revalidation_agent.md, latest Fixing Report, and assigned finding files.

Act as QA Re-validation Agent.
Do not modify production code, tests, or scripts.
Revalidate only these findings: [INSERT FINDING IDS].
Run focused and regression validation. Return QA Re-validation Report only.
```

## 5. Final acceptance prompt

```text
Read AGENTS.md, backend/AGENTS.md, rag/AGENTS.md, .agent/shared_integrated_context.md, .agent/qa_agent.md, and all current open/closed findings.

Act as QA Agent.
Do not modify production code.
Run final integrated Backend + RAG/ML acceptance validation.

Required modes:
1. Backend mock RAG/GenAI mode.
2. Real RAG + mock GenAI mode.
3. Optional real RAG + real GenAI mode only if keys/services are configured.

Do not approve if P1 findings remain open.
Create qa/reports/QA_FINAL_ACCEPTANCE_INTEGRATED_BACKEND_RAG.md.
```
