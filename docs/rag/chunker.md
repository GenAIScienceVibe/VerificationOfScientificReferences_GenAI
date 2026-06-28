# chunker.py — Section-Aware Chunking Module

**SCRUM-179 | rag/ingestion/chunker.py**

---

## What it does

`chunker.py` receives the clean plain text produced by `cleaner.py` and splits
it into small, token-bounded pieces called **chunks**. Each chunk carries
metadata describing which section of the paper it came from, which directly
affects how much weight it receives during similarity search.

The problem being solved: a language model's embedding can only cover ~512
tokens at once. A full scientific paper has thousands of tokens, so we must
cut it into manageable windows. But a naive cut (every N characters) would
break across paragraph and section boundaries, losing the semantic structure
of the paper. This module is aware of sections and respects them.

---

## How to use it

```python
from rag.ingestion.chunker import chunk_text
from rag.ingestion.models import ChunkerInput, EvidenceAvailability

# Build the input (normally you pass the output of clean_text() here)
input_data = ChunkerInput(
    clean_text="Introduction\n\nRegular exercise reduces cardiovascular risk.\n\nMethods\n\nWe enrolled 200 participants...",
    evidence_availability=EvidenceAvailability.FULL_TEXT_AVAILABLE,
    doi="10.1234/example.2019.001",
)

result = chunk_text(input_data)

print(f"Produced {result.total_chunks} chunks")
print(f"Sections found: {result.sections_found}")
print(f"Fallback used: {result.fallback_used}")

for chunk in result.chunks:
    print(chunk.chunk_id, chunk.section, chunk.priority, chunk.token_count)
    print(chunk.chunk_text[:80], "...")
```

### Typical output

```
Produced 4 chunks
Sections found: ['introduction', 'methods']
Fallback used: False

10_1234_example_2019_001_chunk_000  introduction  1.0  18
Regular exercise reduces cardiovascular risk. ...

10_1234_example_2019_001_chunk_001  methods  1.3  47
We enrolled 200 participants ... [split at 512 tokens if needed]
```

---

## The chunking pipeline (step by step)

### Step 1 — Section detection

The module scans the text line by line looking for **heading lines**. A line
is treated as a heading when ALL three conditions hold:

| Condition | Description |
|-----------|-------------|
| Short | Line is under 60 characters |
| Title-like | Is all-caps, OR starts with uppercase + ≤ 8 words + no trailing `.`, OR has a numbered prefix (`1.`, `2.1`, `III.`) |
| Context | The next line is blank, indented, or end-of-document |

The context check is critical — it filters out the first sentence of a
paragraph, which is often short and capitalised but is NOT a heading.

### Step 2 — Section normalisation

The raw heading text (e.g. `"2.1 Experimental Setup"`) is converted to a
standard name:
1. Strip the number prefix → `"Experimental Setup"`
2. Lowercase → `"experimental setup"`
3. Look up in `SECTION_MAP` → `"methods"`

If the name is not in `SECTION_MAP`, it is kept as-is (lowercased) and used
as a custom section label.

### Step 3 — Skip sections

Sections whose normalised name appears in `SKIP_SECTIONS` (References,
Acknowledgements, Funding, etc.) are discarded entirely. These contain
no scientific evidence relevant to claim verification.

### Step 4 — Short paragraph merging

Within each kept section, text is split on double newlines into paragraphs.
Any paragraph shorter than **50 tokens** is merged with the next one. This
prevents nearly-empty chunks that would produce weak embedding vectors.

### Step 5 — Token-bounded splitting

After merging, if a unit still exceeds **512 tokens**, it is passed to
`RecursiveCharacterTextSplitter` (from `langchain-text-splitters`) with:
- `chunk_size = 512` (in tokens)
- `chunk_overlap = 64` (in tokens)
- `length_function = count_tokens` (tiktoken `cl100k_base`)
- `separators = ["\n\n", "\n", ". ", " "]`

The separators are tried from left to right; the splitter picks the widest
break that keeps the chunk within the token limit.

### Step 6 — Fallback

If zero headings are detected (e.g. the source is just an abstract), the
entire text is chunked as one section with `section="unknown"` and
`priority=1.0`. The `fallback_used` flag in the output is set to `True`.

---

## Section priority weights

Sections closer to the scientific claims (Results, Methods) receive higher
weights. These weights are multiplied with the cosine similarity score at
retrieval time to boost the most relevant chunks.

| Section | Weight |
|---------|--------|
| results | 1.3 |
| methods | 1.3 |
| experiments | 1.3 |
| discussion | 1.1 |
| conclusion | 1.1 |
| introduction | 1.0 |
| abstract | 1.0 |
| unknown | 1.0 |
| related_work | 0.8 |
| future_work | 0.8 |

---

## Chunk metadata fields

Every chunk carries this metadata so the retrieval step can filter, sort,
and weight results without needing to re-parse the text:

```python
ChunkMetadata(
    chunk_id       = "10_1234_example_2019_001_chunk_003",  # unique ID
    section        = "results",
    priority       = 1.3,
    chunk_index    = 3,                # zero-based position in the paper
    paper_doi      = "10.1234/...",
    evidence_type  = "FULL_TEXT",      # or "ABSTRACT"
    chunk_text     = "Participants showed a 28% reduction...",
    token_count    = 47,
)
```

---

## Data models

```
ChunkerInput
├── clean_text: str
├── doi: str
└── evidence_availability: EvidenceAvailability

ChunkerOutput
├── doi: str
├── chunks: list[ChunkMetadata]
├── total_chunks: int
├── sections_found: list[str]
└── fallback_used: bool
```

---

## Key design decisions

### Why use tiktoken instead of character count?
Character counts differ drastically between languages and tokenisers. Using
tiktoken with `cl100k_base` (the same encoding used by `text-embedding-3-small`)
ensures the chunk size we set here matches exactly what the embedding model sees.

### Why check heading *context* (blank line after)?
Without it, any short, capitalised sentence at the start of a paragraph
(e.g. "This study had limitations.") would be mistakenly classified as a
heading. Requiring a blank line after the candidate dramatically reduces
false positives.

### Why return an empty list from `split_into_sections` when no headings found?
This allows `chunk_text` to distinguish between "document has no headings at
all" (fallback path, `fallback_used=True`) and "document starts with
unlabelled text followed by real sections" (normal path, first section is
"unknown" but `fallback_used=False`).

### Why build the splitter once at module import?
`RecursiveCharacterTextSplitter` is stateless and cheap to construct, but
building it once at module level avoids repeated object creation on every
call and makes the length function binding explicit and reviewable.

---

## Running the tests

```bash
python -m pytest tests/rag/test_chunker.py -v
```

72 tests covering every function and the full orchestration pipeline.
