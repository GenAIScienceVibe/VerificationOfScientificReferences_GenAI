# INT-QA-012 — Integrated documentation gap

Finding ID: INT-QA-012  
Title: README and environment setup do not document the merged runtime accurately  
Severity: P2  
Status: Open  
Blocking: No  
Component: Docs  
Phase impacted: Integrated QA  
Endpoint/service: Setup and run documentation  
Test type: Manual

## Problem

The repository lacks usable integrated setup, dependency, and mock/real-mode documentation.

## Steps to reproduce

Review root `README.md`, `rag/README.md`, `tests/README.md`, `.env.example`, `backend/.env.example`, and backend README BE9/BE10 sections.

## Expected result

Documentation explains combined or service installation, working directories/PYTHONPATH, all three validation modes, required keys, external-call behavior, and exact backend + RAG commands.

## Actual result

Root README is two lines; `rag/README.md` and `tests/README.md` are blank; root `.env.example` only lists key placeholders. Backend README describes HTTP service settings and future real GenAI despite current direct `rag.api` adapters. It does not instruct users to install `rag/requirements.txt` into a compatible environment or run root RAG tests. Real/mock mode distinctions and Mode 2 execution are absent.

## Evidence

File lengths and content review on 2026-06-28.

## Root cause hypothesis

Documentation was not reconciled after the backend/RAG merge and BE14-style additions.

## Suggested fix direction

Write one authoritative integrated setup/run matrix and link component READMEs to it; remove stale boundary claims.

## Regression risk

Medium. Incorrect setup encourages mock/live confusion and import failures.

## Validation required after fix

Follow the instructions from a clean environment and complete mock tests, RAG tests, Mode 2, and optional Mode 3 without undocumented steps.

## Closure note

Open as of 2026-06-28.
