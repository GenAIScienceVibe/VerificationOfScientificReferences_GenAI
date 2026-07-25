# Integrated Backend + RAG/ML QA Runbook

## Goal

Validate the latest merged package before it is accepted as a true Backend + RAG/ML integration.

## Important note

The old BE13 backend already passed final QA in mock mode. The current task is to validate the newly merged RAG/ML and BE14-style full-text functionality.

## Step 0 — manual backup

Because the user may not use Git, make a manual backup before any Codex development/fixing task:
```bash
cd ..
cp -r VerificationOfScientificReferences_GenAI VerificationOfScientificReferences_GenAI_BACKUP_BEFORE_INTEGRATION_FIXES
```

## Step 1 — baseline QA

Run Codex with `.agent/qa_agent.md` and save:
```text
qa/reports/QA_INTEGRATED_BASELINE_REPORT.md
```

## Step 2 — fix only P1 blockers

Start with:
- INT-QA-001
- INT-QA-002
- INT-QA-003
- INT-QA-004
- INT-QA-006

Do not attempt full Door 2 live GenAI until Door 1 real RAG is validated.

## Step 3 — revalidate findings

Every fix must be revalidated by QA Re-validation Agent.

## Step 4 — staged integration acceptance

Required before final acceptance:
1. Backend mock mode passes.
2. RAG unit tests pass.
3. Real RAG import works.
4. Real RAG + mock GenAI pipeline passes.
5. Real-PDF validation passes.
6. No P1 findings remain open.

## Step 5 — final documentation

Update:
- root README
- backend README
- rag README
- docs/integration notes
- QA reports
- finding statuses

## Do not approve if

- real RAG cannot import
- root RAG tests fail
- RAG scores exceed 1
- backend `FOUND` DOI maps to RAG `VALID`
- metadata disabled mode makes external calls
- real RAG ignores top_k
- unsupported support labels appear
- BE11 safety is bypassed
