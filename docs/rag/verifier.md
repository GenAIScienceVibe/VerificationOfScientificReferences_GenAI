# verifier.py — SCRUM-193

## What it does

`rag/prompts/verifier.py` is Door 2's core LLM call. It:

1. Renders `templates/verify.j2` with the claim, citation type, DOI, and
   the retrieved evidence chunks (each tagged with its section).
2. Sends the rendered prompt to Llama 4 Scout via OpenRouter at
   `temperature=0`.
3. Returns the raw response text.

The raw text is expected to be a JSON string matching the
`VerificationOutput` schema (SCRUM-194), but this module does **not** parse
or validate it — that happens in `rag/verification/validator.py`
(SCRUM-253). Keeping rendering/calling separate from parsing/validating
makes each module testable in isolation.

---

## How to use it

```python
from rag.prompts.verifier import generate_verdict
from rag.verification.models import VerificationInput

raw_response = generate_verdict(VerificationInput(
    claim_text="Exercise reduces heart disease risk by 35%",
    citation_type="RESULT_COMPARISON",
    chunks=top_chunks,              # list[ChunkMetadata] from retrieval
    doi="10.1234/example.2019.001",
))
# raw_response is a JSON string — pass to validator.py next
```

### Input / output

| | |
|---|---|
| Input | `VerificationInput` — `claim_text`, `citation_type`, `chunks`, `doi` |
| Output | `str` — raw LLM response text (expected to be JSON) |

---

## Key design decisions

### `render_prompt()` is a pure function

Separating prompt rendering from the API call means the prompt text itself
can be unit-tested directly — no mocking required — while
`generate_verdict()`'s tests only need to mock the OpenAI client and can
trust the prompt content is already covered.

### `temperature=0` via shared constant

Imports `LLM_TEMPERATURE` from `rag/prompts/config.py` (SCRUM-254). The same
claim and evidence must always produce the same verdict.

### Jinja2 environment built once at import time

Unlike the OpenAI client (deferred because it depends on an env var that
may not be set), the Jinja2 `Environment` only depends on the fixed
`templates/` directory next to this file, so there's no benefit to lazy
construction — it's built once at module import.

### JSON-only instruction in the prompt, not in code

The template explicitly tells the LLM to respond with *only* a JSON object,
no markdown fences or commentary. This keeps the parsing contract simple
for `validator.py`, which can attempt `json.loads()` directly on the raw
response without stripping markdown first.

### Raw text returned, not a parsed object

`generate_verdict()` returns the raw string rather than attempting to parse
or construct a `VerificationOutput`. Malformed JSON, missing fields, or a
hallucinated verdict label are all possible LLM failure modes — handling
them is explicitly validator.py's job (SCRUM-253), not this module's.

---

## Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `LLM_MODEL` | `"meta-llama/llama-4-scout"` | Model used for verification, via OpenRouter |
| `TEMPLATES_DIR` | `Path(__file__).parent / "templates"` | Directory Jinja2 loads templates from |
| `TEMPLATE_NAME` | `"verify.j2"` | Template file rendered by `render_prompt()` |
| `SYSTEM_PROMPT` | str | Instructs the LLM to respond with JSON only |

## Template: `templates/verify.j2`

Inputs: `claim_text`, `citation_type`, `doi`, `chunks` (each with `chunk_id`,
`section`, `chunk_text`). Falls back to "No evidence chunks were retrieved
for this source." when `chunks` is empty, so the verifier can still be
called for an `INSUFFICIENT_EVIDENCE` case without a template error.

Chain-of-thought reasoning instructions will be added to this template in
SCRUM-195 (Task 11).
