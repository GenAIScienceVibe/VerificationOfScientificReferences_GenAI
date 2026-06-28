# BE-6 Integration Note

Implemented BE-6 — Claim and Citation Management on top of BE-5 DOI Metadata Lookup and the stable BE4.2 reference/DOI quality baseline.

Key protection rule: BE4.2 reference splitting / DOI attachment and BE-5 metadata lookup services were preserved. BE-6 adds claim/citation services and APIs without changing external metadata lookup behavior.

Default claim extraction mode is `local_deterministic`, which is backend-controlled and mockable. It preserves the future internal GenAI contract while avoiding live GenAI calls in local tests.
