# cleaner.py — Text Cleaning Module

**SCRUM-178 | rag/ingestion/cleaner.py**

---

## What it does

`cleaner.py` receives raw plain text (already extracted from a PDF by the backend) and returns clean text ready for the section-aware chunker.

Scientific papers, when converted from PDF to plain text, contain a lot of noise:
- Running headers and footers repeated on every page (journal name, paper title)
- Page numbers on their own line
- Excessive whitespace from column-layout artifacts
- A references/bibliography section at the end that we must not embed as evidence

This module removes all of that and returns clean, readable prose.

---

## How to use it

```python
from rag.ingestion.cleaner import clean_text
from rag.ingestion.models import CleanerInput, EvidenceAvailability

# Build input (this comes from Door 1 — the backend sends us source_evidence.text)
input_data = CleanerInput(
    raw_text="Journal of Science\nPage 1\nIntroduction\n...\nReferences\n[1] Smith 2020",
    evidence_availability=EvidenceAvailability.FULL_TEXT_AVAILABLE,
    doi="10.1234/example.2019.001",
)

result = clean_text(input_data)

print(result.clean_text)          # cleaned string
print(result.original_length)     # char count before cleaning
print(result.cleaned_length)      # char count after cleaning
```

The output `CleanerOutput` is passed directly to the chunker in the next step.

---

## Cleaning steps (in order)

| Step | What it does | Why |
|------|-------------|-----|
| 1. Normalize whitespace | CRLF → LF, tabs → spaces, collapse multi-spaces | PDF converters produce inconsistent whitespace |
| 2. Remove page numbers | Strip lines matching `Page 3`, `3 of 12`, `- 3 -`, bare digits | Page markers appear on their own line in PDF text |
| 3. Remove repeated lines | Count line frequency; strip lines appearing 3+ times | Running headers/footers repeat on every page |
| 4. Remove references section | Cut from the last "References" / "Bibliography" heading to end | We do not want cited works embedded as evidence |
| 5. Collapse blank lines | Reduce 3+ consecutive blank lines to 2 | PDF layout artifacts produce excessive whitespace |

---

## Key design decisions

### Why cut on the *last* "References" heading?
The body of a paper often contains phrases like "as shown in the References section above." If we cut on the *first* match, we'd lose part of the paper body. Searching for the last occurrence reliably targets the actual reference list.

### Why use line frequency for headers/footers?
Running headers are not identifiable by content — a journal title differs per paper. But they share a structural property: they repeat on every page. Counting line frequency and removing lines that appear 3+ times captures this pattern without any hardcoded strings.

### Why threshold = 3?
A line that appears twice could legitimately be a repeated concept in the text. Three or more times, on a line under 120 characters, is statistically almost always a header/footer. The threshold is a module-level constant (`REPEATED_LINE_THRESHOLD`) so it can be tuned.

### Why keep it pure (no external dependencies)?
The cleaner uses only Python's standard library (`re`, `collections`). This makes it fast, easy to test, and free from version conflicts. The LLM/embedding dependencies are only needed in later pipeline stages.

---

## Data models

```
CleanerInput
├── raw_text: str                          # from backend
├── evidence_availability: EvidenceAvailability  # FULL_TEXT / ABSTRACT
└── doi: str                               # for logging

CleanerOutput
├── clean_text: str                        # → goes to chunker
├── doi: str                               # passed through
├── evidence_availability: EvidenceAvailability  # passed through
├── original_length: int                   # chars before cleaning
└── cleaned_length: int                    # chars after cleaning
```

---

## Running the tests

```bash
python -m pytest tests/rag/test_cleaner.py -v
```

30 tests covering all individual helpers and the full orchestration pipeline.
