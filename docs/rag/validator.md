# validator.py — SCRUM-253

## What it does

`rag/verification/validator.py` is the last step of Door 2: it takes the
raw JSON string returned by `rag.prompts.verifier.generate_verdict()` and
turns it into a validated `VerificationOutput`. If anything about the raw
response is wrong — malformed JSON, a missing field, an unrecognised
verdict label, an out-of-range confidence — the failure is logged and a
safe `NEEDS_HUMAN_REVIEW` fallback is returned instead of raising. An LLM
response that fails validation must never crash the pipeline or silently
propagate bad data to the backend.

---

## How to use it

```python
from rag.prompts.verifier import generate_verdict
from rag.verification.validator import validate_output

raw_json = generate_verdict(verification_input)
output = validate_output(raw_json, low_confidence=vector_store_output.low_confidence)
# output is always a valid VerificationOutput, never raises
```

### Input / output

| | |
|---|---|
| Input | `raw_json: str` — raw LLM response text, `low_confidence: bool = False` — from `VectorStoreOutput` |
| Output | `VerificationOutput` — always, even on failure (as a `NEEDS_HUMAN_REVIEW` fallback) |

---

## Key design decisions

### Reuses `attach_human_review_flag()` instead of recomputing the rule

`rag/prompts/verifier.py` (SCRUM-196) already implements the
`human_review_required` rule. `validate_output()` calls
`attach_human_review_flag()` to both parse the JSON and inject the flag in
one step, rather than duplicating `confidence < 0.5 OR verdict ==
PARTIALLY_SUPPORTED OR low_confidence` logic here.

### Three distinct failure modes, three log messages

| Failure | Caught from | Log message contains |
|---|---|---|
| Malformed JSON | `json.JSONDecodeError` (raised by `attach_human_review_flag`) | "not valid JSON" |
| Missing `verdict`/`confidence` | `KeyError` (raised by `attach_human_review_flag`) | "missing required field" |
| Any other schema mismatch (bad verdict label, out-of-range confidence, missing `explanation`, etc.) | `pydantic.ValidationError` (raised by `VerificationOutput(**data)`) | "does not match VerificationOutput schema" |

Distinguishing these in the log message makes it clear during debugging
*why* a particular LLM call needed a fallback, without needing to inspect
the raw response separately.

### Fallback is itself a valid `VerificationOutput`

`_fallback_output()` constructs a real `VerificationOutput` instance
(`verdict=NEEDS_HUMAN_REVIEW`, `confidence=0.0`, `human_review_required=True`)
rather than returning `None` or raising. Callers always get back a
type-correct object they can pass straight to the backend.

---

## Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `FALLBACK_EXPLANATION_PREFIX` | `"Automatic NEEDS_HUMAN_REVIEW fallback — LLM output failed validation"` | Prefix on the `explanation` field of every fallback output, so it's identifiable in logs/DB without parsing |
