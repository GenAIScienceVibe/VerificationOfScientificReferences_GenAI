# BE-4.1 Integration Note

BE-4.1 has been integrated on top of BE-4.

## Confirmed previous phases

- BE-1 Backend Foundation remains present.
- BE-2 Database Design remains present.
- BE-3 Document Upload and Text Processing remains present.
- BE-4 Reference and DOI Extraction remains present.

## BE-4.1 hardening added

- Better references boundary detection.
- Header/footer/page artifact cleanup.
- DOI continuation repair.
- Stricter malformed DOI detection.
- Better reference splitting and false-positive filtering.
- Invalid filter validation.
- Raw text debug gating.
- Safer reference re-extraction blocking when downstream records exist.
- Failed PDF audit visibility.
- Real-PDF regression fixtures and QA script.

## Explicitly deferred

No DOI metadata lookup, CrossRef/OpenAlex calls, claim extraction, citation mapping, evidence package building, RAG retrieval, GenAI verification, report generation, or feedback workflows were added.
