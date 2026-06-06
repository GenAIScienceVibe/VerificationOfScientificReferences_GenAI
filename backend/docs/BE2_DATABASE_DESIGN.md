# BE-2 — Database Design

This document describes the BE-2 database design for the verifAI / RefCheck AI backend.

## Scope

BE-2 implements database support only. It prepares persistence for the complete verification workflow but does not implement PDF parsing, reference extraction, DOI metadata lookup, claim extraction, RAG retrieval, GenAI verification, safety scoring, report generation, or feedback workflows.

## Technology

- SQLAlchemy ORM 2.x
- SQLite fallback for local/demo use
- PostgreSQL-compatible model design through `DATABASE_URL`
- Thin repository/data-access layer
- SQLAlchemy metadata initialization through `scripts/init_db.py`

Alembic is intentionally not introduced in BE-2 to keep the course demo simple. A future hardening phase can add Alembic migrations without renaming the models or tables.

## Configuration

Set the database in `.env`:

```env
DATABASE_URL="sqlite:///./data/refcheck_be2.db"
```

For PostgreSQL later:

```env
DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/refcheck"
```

Do not hardcode credentials.

## Initialization

```bash
cd backend
python scripts/init_db.py
```

The FastAPI app also initializes the local/demo tables on startup through `app.db.init_db.init_db()`.

## Core entities

BE-2 creates these tables:

1. `documents`
2. `document_sections`
3. `references`
4. `source_metadata`
5. `claims`
6. `citations`
7. `claim_reference_links`
8. `evidence_packages`
9. `rag_retrieval_results`
10. `verification_results`
11. `safety_checks`
12. `reports`
13. `user_feedback`
14. `uat_surveys`
15. `pipeline_runs`
16. `pipeline_steps`
17. `prompt_runs`
18. `claim_cache_index`

## Important relationships

- Document has many sections, references, claims, citations, pipeline runs, verification results, reports, feedback entries, and surveys.
- Reference belongs to a document and has metadata records.
- Claim belongs to a document and connects to references through claim-reference links.
- Citation can map a claim to a reference.
- Evidence packages connect document, claim, and reference.
- RAG retrieval results belong to claim/reference/evidence package.
- Verification results belong to document, claim, and reference.
- Safety checks belong to verification results.
- Pipeline steps belong to pipeline runs.
- Prompt runs may belong to document, claim, or pipeline run.
- Cache entries link normalized claim + DOI + versions to a verification result.

## Required enums

Implemented in `app/models/enums.py`:

- `DocumentStatus`
- `PipelineStatus`
- `PipelineStepStatus`
- `DoiStatus`
- `MetadataStatus`
- `ClaimType`
- `MappingStatus`
- `EvidenceAvailability`
- `SupportStatus`
- `CacheSource`
- `SafetyRiskLevel`
- `UploadType`

## Repository layer

Thin repositories are implemented for:

- `DocumentRepository`
- `ReferenceRepository`
- `ClaimRepository`
- `PipelineRepository`
- `VerificationResultRepository`

These are intentionally persistence-only. Workflow/business logic belongs to later phases.

## Seed/demo data

```bash
cd backend
python scripts/seed_demo_data.py
```

The seed script creates one demo document, one reference, one claim, one claim-reference link, and one verification result. It is clearly demo data only.

## BE-1 endpoint impact

The BE-1 document stubs are now database-backed:

- `POST /api/v1/documents/text` stores a `Document` record.
- `POST /api/v1/documents/upload` stores a `Document` record and uploaded file path.
- `GET /api/v1/documents/{document_id}` reads from the database.
- `GET /api/v1/documents/{document_id}/status` reads document status from the database.

No BE-3 document processing logic is implemented.
