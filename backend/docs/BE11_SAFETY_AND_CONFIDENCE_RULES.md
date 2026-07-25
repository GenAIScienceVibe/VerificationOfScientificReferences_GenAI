# BE-11 — Safety and Confidence Rules

## Purpose
BE-11 adds a deterministic backend safety and confidence layer on top of BE-10 GenAI verification orchestration. GenAI and RAG outputs are not treated as final authority. The backend evaluates DOI status, metadata status, evidence availability, RAG similarity, GenAI confidence, cache source, and evidence-used consistency before exposing final verification results.

## Final support labels
Only the final project labels are allowed:

- `SUPPORTED`
- `PARTIALLY_SUPPORTED`
- `NOT_SUPPORTED`
- `INSUFFICIENT_EVIDENCE`
- `NEEDS_HUMAN_REVIEW`

Product-facing labels such as `Hallucinated`, `TRUE`, `FALSE`, `VERIFIED`, `CONTRADICTED`, or `UNKNOWN` are not used.

## Safety policy service
The main implementation is:

```text
app/services/safety_policy.py
```

It provides:

- `SafetyPolicyService.evaluate_and_apply(...)`
- deterministic rule evaluation
- confidence capping
- final status override
- `SafetyCheck` persistence
- document-level safety summary
- result-level safety-check retrieval

## Rules implemented
BE-11 implements the required backend safety rules, including:

- Missing DOI → `NEEDS_HUMAN_REVIEW`
- Invalid DOI → `NEEDS_HUMAN_REVIEW`
- Malformed DOI → `NEEDS_HUMAN_REVIEW`
- Metadata unavailable → `INSUFFICIENT_EVIDENCE` / review
- Source unavailable → `INSUFFICIENT_EVIDENCE` and confidence cap
- Metadata-only supported result → review/cap
- Low similarity → `NEEDS_HUMAN_REVIEW`
- Medium similarity + supported result → downgrade toward partial/review behavior
- Low GenAI confidence → `NEEDS_HUMAN_REVIEW`
- GenAI supported + weak evidence → `NEEDS_HUMAN_REVIEW`
- Evidence-used chunk mismatch → `NEEDS_HUMAN_REVIEW`
- Cache results are checked for confidence, DOI safety, and review status

## Configurable thresholds
Configured through `.env` / settings:

```text
SAFETY_MIN_GENAI_CONFIDENCE=0.60
SAFETY_MIN_STRONG_SIMILARITY=0.80
SAFETY_MIN_ACCEPTABLE_SIMILARITY=0.60
SAFETY_LOW_SIMILARITY_THRESHOLD=0.60
SAFETY_REQUIRE_VALID_DOI_FOR_SUPPORTED=true
SAFETY_REQUIRE_EVIDENCE_FOR_SUPPORTED=true
SAFETY_FLAG_METADATA_ONLY_SUPPORTED=true
SAFETY_FLAG_SOURCE_UNAVAILABLE=true
SAFETY_ENABLE_GENAI_RAG_CONFLICT_CHECK=true
SAFETY_MAX_CONFIDENCE_WITH_METADATA_ONLY=0.70
SAFETY_MAX_CONFIDENCE_WITH_SOURCE_UNAVAILABLE=0.40
SAFETY_MAX_CONFIDENCE_WITH_LOW_SIMILARITY=0.55
SAFETY_POLICY_VERSION=policy-v1
```

## Confidence capping
BE-11 never increases confidence. It can only preserve or reduce confidence.

Examples:

- Source unavailable → max confidence `0.40`
- Metadata-only evidence → max confidence `0.70`
- Low similarity → max confidence `0.55`
- Invalid GenAI or fallback → safe low confidence

## SafetyCheck persistence
Each triggered rule creates a `SafetyCheck` row with:

- `verification_result_id`
- `safety_status`
- `risk_level`
- `issue`
- `recommended_action`
- `backend_rule_triggered`

Multiple checks can be stored for one verification result.

## API updates
BE-11 keeps BE-10 result APIs and adds safety visibility:

```text
GET /api/v1/verification-results/{result_id}
GET /api/v1/documents/{document_id}/verification-results
GET /api/v1/verification-results/{result_id}/safety-checks
GET /api/v1/documents/{document_id}/safety-summary
```

Frontend-facing results now expose:

- `safety_risk_level`
- `safety_status`
- `safety_rules_triggered`
- `human_review_required`
- detailed safety checks in result detail responses

## Uploaded research-paper validation
The BE-11 validation script processes the provided PDFs through BE-3 to BE-11 using mock RAG/GenAI and deterministic safety rules:

```bash
python scripts/validate_uploaded_pdfs_be11.py --reset-db \
  /path/to/IRRDOLPUBLISHEDARTICLE.pdf \
  /path/to/Impact_of_Ease_of_Use_Usefulness_Attitude_and_Trus.pdf \
  /path/to/SeminarPaper_20.01..pdf
```

Results are stored in:

```text
validation/uploaded_pdf_validation_be11_output.txt
```

## Limitations

- BE-11 does not generate reports. That belongs to BE-12.
- BE-11 does not create frontend UI.
- BE-11 does not replace human academic review.
- BE-11 does not prove scientific truth. It checks evidence support and flags uncertainty.
- Validation uses mock RAG/GenAI unless real services are configured.
