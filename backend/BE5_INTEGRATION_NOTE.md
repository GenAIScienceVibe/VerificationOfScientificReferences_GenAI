# BE-5 Integration Note

This package implements BE-5 - DOI Metadata Lookup on top of the stable BE4.2 baseline.

Previous phases preserved:

- BE-1 Backend Foundation
- BE-2 Database Design
- BE-3 Document Upload and Text Processing
- BE-4 / BE4.2 Reference and DOI Extraction Quality

New BE-5 endpoints:

- `POST /api/v1/references/{reference_id}/verify-doi`
- `POST /api/v1/documents/{document_id}/verify-dois`
- `GET /api/v1/references/{reference_id}/metadata`

No BE-6+ logic is implemented.
