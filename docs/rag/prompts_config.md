# config.py (prompts) — SCRUM-254

## What it does

`rag/prompts/config.py` holds `LLM_TEMPERATURE`, the single source of truth
for the temperature used on every chat-completion call in the codebase.

## How to use it

```python
from rag.prompts.config import LLM_TEMPERATURE

response = client.chat.completions.create(
    model="meta-llama/llama-4-scout",
    temperature=LLM_TEMPERATURE,
    messages=[...],
)
```

`classifier.py` (SCRUM-252) and `verifier.py` (SCRUM-193) must both import
this constant instead of hardcoding `0` directly.

## Key design decisions

### One constant, not a hardcoded `0` in every call site

Verification verdicts must be reproducible: the same claim and evidence
should always produce the same verdict. Hardcoding `temperature=0` in two
separate files risks one of them drifting (e.g. someone bumps it to `0.2`
for "better explanations" in only one place). A single imported constant
makes the requirement impossible to violate accidentally and easy to audit
— `grep -rn LLM_TEMPERATURE` finds every call site instantly.

### Audit finding (SCRUM-254)

At the time of this audit, the only existing API call in the codebase is
`embeddings.create()` in `rag/retrieval/embedder.py`, which has no
`temperature` parameter (embeddings are deterministic by nature). No
chat-completion call sites exist yet — `classifier.py` and `verifier.py`
are still pending (Tasks 9 and 10). This module exists so those modules
have a constant to import from day one.
