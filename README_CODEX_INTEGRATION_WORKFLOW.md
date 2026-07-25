# Codex Workflow for Latest Integrated Backend + RAG/ML Package

## Purpose

This package contains the latest integrated Backend + RAG/ML code. It needs a controlled Codex workflow to fix and validate live RAG/ML integration without breaking the previously accepted BE13 backend.

## Agent files added

- `AGENTS.md`
- `backend/AGENTS.md`
- `rag/AGENTS.md`
- `.agent/shared_integrated_context.md`
- `.agent/development_agent.md`
- `.agent/qa_agent.md`
- `.agent/fixing_agent.md`
- `.agent/revalidation_agent.md`
- `.agent/codex_task_prompts.md`
- `.agent/live_rag_validation_protocol.md`
- `qa/INTEGRATED_QA_RUNBOOK.md`
- `qa/findings/INTEGRATED_QA_FINDING_TEMPLATE.md`
- `qa/findings/INTEGRATED_QA_INITIAL_FINDINGS.md`
- `docs/integration/INTEGRATED_BACKEND_RAG_ISSUE_REGISTER.md`
- `qa/real_rag_validation/integration_validation_matrix.md`

## Recommended process

1. Make a manual folder/ZIP backup.
2. Run QA Agent baseline.
3. Development Agent fixes first P1 integration blockers.
4. QA Re-validation Agent revalidates only fixed findings.
5. Run real RAG + mock GenAI validation.
6. Only then consider real GenAI validation.

## First Codex task

Use `.agent/codex_task_prompts.md` → Baseline QA prompt.

## First development task

Use `.agent/codex_task_prompts.md` → Development prompt for first blocker group.

## Do not approve until

- INT-QA-001, 002, 003, 004, 006 are fixed and revalidated.
- Real RAG + mock GenAI pipeline passes.
- No P1 findings remain open.
