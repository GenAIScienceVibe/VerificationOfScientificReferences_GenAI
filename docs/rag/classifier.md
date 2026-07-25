# classifier.py — SCRUM-252

## What it does

`rag/prompts/classifier.py` makes one LLM call via OpenRouter to classify a
clean claim into one of six citation types:

- `RESULT_COMPARISON` — claim compares/reports a specific numeric or
  experimental result from the source
- `METHOD` — claim describes a technique, algorithm, or procedure
- `BACKGROUND` — claim cites the source for general context or prior
  knowledge
- `MOTIVATION` — claim cites the source to justify why the current work
  matters
- `EXTENSION` — claim says the current work builds on or extends the source
- `FUTURE_WORK` — claim cites the source as a direction for future research

This label is later passed into `verifier.py` (SCRUM-193) so the LLM
verification prompt has the right context for judging the claim.

---

## How to use it

```python
from rag.prompts.classifier import classify_citation_type

citation_type = classify_citation_type("The algorithm follows the approach of Smith et al.")
# CitationType.METHOD
```

### Input / output

| | |
|---|---|
| Input | `claim_text: str` — clean factual claim (author names already stripped) |
| Output | `CitationType` — one of the six labels, or `BACKGROUND` on any failure |

---

## Key design decisions

### Fallback to `BACKGROUND`, not an exception

Classification only adds context to the verification prompt — it is not a
pipeline-critical step like embedding. If the API key is missing, the
network call fails, or the LLM returns something unparseable, we log a
warning and return `CitationType.BACKGROUND` (the safest, most general
category) rather than raising and blocking the rest of the pipeline.

### `temperature=0` via shared constant

Imports `LLM_TEMPERATURE` from `rag/prompts/config.py` (SCRUM-254) instead
of hardcoding `0`. The same claim must always classify the same way.

### Strict label parsing

`_parse_label` strips whitespace and uppercases the raw LLM response, then
constructs a `CitationType` enum member directly — any string that isn't
exactly one of the six labels raises `ValueError`, which `classify_citation_type`
catches and turns into the `BACKGROUND` fallback. This guards against the
LLM adding extra words, punctuation, or a label we don't recognise.

### Lazy client construction

`_build_client()` is called inside `classify_citation_type()`, not at
import time, so tests can import and patch this module without a real
`OPENROUTER_API_KEY` present — same pattern as `embedder.py`.

---

## Module-level constants

| Constant | Value | Purpose |
|---|---|---|
| `LLM_MODEL` | `"meta-llama/llama-4-scout"` | Model used for classification, via OpenRouter |
| `DEFAULT_CITATION_TYPE_VALUE` | `"BACKGROUND"` | Fallback label string |
| `DEFAULT_CITATION_TYPE` | `CitationType.BACKGROUND` | Fallback enum member |
| `SYSTEM_PROMPT` | str | Instructs the LLM to output exactly one label and nothing else |
