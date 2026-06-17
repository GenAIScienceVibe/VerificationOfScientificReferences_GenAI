# BE-7 Integration Note
Implemented BE-7 — Evidence Package Builder on top of BE-6 (Claim & Citation Management) and BE-5 (DOI Metadata Lookup).

Key protection rule: BE-6 claim/citation services and BE-5 metadata lookup were preserved. BE-7 adds evidence package building without changing any upstream extraction or lookup behavior.

Evidence packages are built from existing ClaimReferenceLink rows with mapping_status == MAPPED. One package per unique (claim, reference) pair. Evidence levels are assigned strictly based on what is actually stored in the database — FULL_TEXT_AVAILABLE is never assigned because no full-text retrieval exists yet.

RAG dispatch is implemented as a placeholder interface (_send_to_rag_service()) so the RAG team can wire in their real service at merge time without changing any call sites.

Placeholder — Task 5 (Send to RAG/ML service): _send_to_rag_service() in evidence_service.py returns len(packages) without contacting any external service. Real HTTP call to the RAG/ML endpoint must be added by the RAG team at merge time. URL, authentication, and request/response schema were not available during BE-7 implementation