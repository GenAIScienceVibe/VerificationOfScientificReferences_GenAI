"""
Section-aware text chunking module for the verifAi RAG pipeline (SCRUM-179).

Responsibility: receive clean plain text (from cleaner.py) and split it into
token-bounded chunks, each labelled with its section name, priority weight,
and full metadata required by the embedding and retrieval steps.

Pipeline within this module:
  1. Detect section headings by scanning lines for title-like patterns.
  2. Normalise heading text → standard section name via SECTION_MAP.
  3. Discard any sections in SKIP_SECTIONS (references, acknowledgements …).
  4. Within each kept section, merge paragraphs that are too short (<50 tokens)
     so we never embed nearly-empty chunks.
  5. Split paragraphs that exceed 512 tokens using RecursiveCharacterTextSplitter
     with tiktoken as the length function.
  6. Tag every chunk with its section, priority, DOI, and evidence type.
  Fallback: if zero headings are detected, chunk the full text blindly and
  tag everything section="unknown", priority=1.0.
"""

import logging
import re
from typing import Optional

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.ingestion.models import (
    ChunkMetadata,
    ChunkerInput,
    ChunkerOutput,
    EvidenceAvailability,
)

logger = logging.getLogger(__name__)

# ── Chunk-size constants ──────────────────────────────────────────────────────

TARGET_CHUNK_SIZE = 512    # tokens — maximum tokens per chunk
MIN_PARAGRAPH_TOKENS = 50  # tokens — paragraphs smaller than this are merged
CHUNK_OVERLAP = 64         # tokens — overlap between consecutive chunks (within 50-75 range)
TIKTOKEN_ENCODING = "cl100k_base"  # matches text-embedding-3-small's tokeniser

# ── Section configuration (from CLAUDE.md) ───────────────────────────────────

SECTION_MAP: dict[str, str] = {
    # Methods variations
    "methodology": "methods",
    "materials and methods": "methods",
    "materials & methods": "methods",
    "experimental setup": "methods",
    "experimental methods": "methods",
    "approach": "methods",
    "procedure": "methods",
    "implementation": "methods",
    "system design": "methods",
    # Results variations
    "findings": "results",
    "experimental results": "results",
    "outcomes": "results",
    "evaluation": "results",
    "performance": "results",
    "experiments": "results",
    "experimental evaluation": "results",
    # Discussion variations
    "analysis": "discussion",
    "interpretation": "discussion",
    "implications": "discussion",
    "results and discussion": "discussion",
    # Related work variations
    "literature review": "related_work",
    "background": "related_work",
    "prior work": "related_work",
    "previous work": "related_work",
    "state of the art": "related_work",
    # Conclusion variations
    "conclusions": "conclusion",
    "summary": "conclusion",
    "concluding remarks": "conclusion",
    "conclusions and future work": "conclusion",
    # Introduction variations
    "overview": "introduction",
    "motivation": "introduction",
    "problem statement": "introduction",
}

SKIP_SECTIONS: list[str] = [
    "references", "bibliography", "acknowledgements", "acknowledgments",
    "author contributions", "funding", "conflict of interest",
    "appendix", "supplementary material", "about the authors",
    "copyright", "license",
]

SECTION_WEIGHTS: dict[str, float] = {
    "results": 1.3,
    "methods": 1.3,
    "experiments": 1.3,
    "discussion": 1.1,
    "conclusion": 1.1,
    "introduction": 1.0,
    "abstract": 1.0,
    "related_work": 0.8,
    "future_work": 0.8,
    "unknown": 1.0,
}

# ── Heading-detection regex ───────────────────────────────────────────────────

# Matches lines that start with a numbered prefix like "1.", "2.1", "III.", "IV."
_NUMBERED_PREFIX_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXivx]{1,6}[.\s]\s*)\S",
    re.IGNORECASE,
)

# Used to strip the number prefix when normalising a heading to its plain name.
_STRIP_PREFIX_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+|[IVXivx]{1,6}[.\s]\s*)",
    re.IGNORECASE,
)

# ── Token counter ─────────────────────────────────────────────────────────────

_tokeniser = tiktoken.get_encoding(TIKTOKEN_ENCODING)


def count_tokens(text: str) -> int:
    """Return the number of tokens in *text* using the cl100k_base encoding."""
    return len(_tokeniser.encode(text))


# ── Splitter (built once, reused across calls) ────────────────────────────────

# We pass count_tokens as the length_function so that chunk_size and
# chunk_overlap are measured in tokens, not characters.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=TARGET_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=count_tokens,
    separators=["\n\n", "\n", ". ", " "],
    keep_separator=False,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _doi_to_id(doi: str) -> str:
    """Convert a DOI string to a safe alphanumeric slug for use in chunk IDs."""
    return re.sub(r"[^\w]", "_", doi).strip("_")


def _evidence_type(availability: EvidenceAvailability) -> str:
    """Map EvidenceAvailability → the evidence_type string stored on each chunk."""
    if availability == EvidenceAvailability.FULL_TEXT_AVAILABLE:
        return "FULL_TEXT"
    return "ABSTRACT"


def _looks_like_heading(stripped: str) -> bool:
    """
    Return True if the line content looks like a section heading.

    A line is considered a heading candidate if it:
      - Has a numbered prefix (1., 2.1, III.), OR
      - Is entirely uppercase (like "ABSTRACT"), OR
      - Starts with an uppercase letter, has at most 8 words, and does not end
        with a sentence-terminating punctuation mark.

    The caller is responsible for the length (<60 chars) and context
    (followed by blank/indented line) checks.
    """
    if not stripped:
        return False

    # Numbered heading is always a strong signal regardless of capitalisation.
    if _NUMBERED_PREFIX_RE.match(stripped):
        return True

    words = stripped.split()

    # All-caps word sequence: "ABSTRACT", "INTRODUCTION AND OVERVIEW"
    if all(w.isupper() for w in words if w.isalpha()) and any(w.isalpha() for w in words):
        return True

    # Title-like phrase: starts with uppercase, short, no trailing period/comma.
    if (
        words
        and words[0][0].isupper()
        and not stripped.endswith(".")
        and not stripped.endswith(",")
        and len(words) <= 8
    ):
        return True

    return False


def _is_heading(line: str, next_line: Optional[str]) -> bool:
    """
    Return True if *line* is a section heading.

    Combines the content heuristic (_looks_like_heading) with the structural
    context: a real heading is followed by a blank line, an indented paragraph,
    or is the last line of the document.
    """
    stripped = line.strip()

    # Hard constraints: non-empty and under 60 characters.
    if not stripped or len(stripped) >= 60:
        return False

    if not _looks_like_heading(stripped):
        return False

    # Context check: must be followed by blank line, indented line, or EOF.
    if next_line is None:
        return True
    if next_line.strip() == "":
        return True
    if next_line and next_line[0] in (" ", "\t"):
        return True

    return False


def normalize_section_name(heading: str) -> str:
    """
    Convert a raw heading string to a canonical section name.

    Steps:
      1. Strip leading number/roman-numeral prefix ("2.1 ", "III. ").
      2. Lowercase and trim whitespace.
      3. Look up the result in SECTION_MAP for known aliases.
      4. If not found, return the lowercased text as-is so it can still be
         matched against SKIP_SECTIONS or used as an unknown section label.
    """
    # Remove leading number or roman numeral prefix
    cleaned = _STRIP_PREFIX_RE.sub("", heading).strip().lower()
    # Remove trailing punctuation (colons, periods sometimes appear on headings)
    cleaned = cleaned.rstrip(".:;")

    return SECTION_MAP.get(cleaned, cleaned)


def should_skip_section(section_name: str) -> bool:
    """Return True if this section should be excluded from chunking."""
    return section_name in SKIP_SECTIONS


# ── Section splitting ─────────────────────────────────────────────────────────


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Parse clean text into a list of (section_name, section_text) pairs.

    Strategy:
      - Walk through lines one at a time.
      - When a heading is detected, close the current section and start a new one.
      - Content before the first heading is labelled "unknown".
      - Sections whose name appears in SKIP_SECTIONS are silently dropped.

    Returns:
        List of (section_name, content) tuples, in document order.
        Sections with no content after stripping are omitted.
    """
    lines = text.split("\n")
    n = len(lines)

    sections: list[tuple[str, str]] = []
    current_section = "unknown"
    current_lines: list[str] = []
    heading_found = False

    for i, line in enumerate(lines):
        next_line = lines[i + 1] if i + 1 < n else None

        if _is_heading(line, next_line):
            heading_found = True
            # Save the accumulated content of the previous section.
            content = "\n".join(current_lines).strip()
            if content and not should_skip_section(current_section):
                sections.append((current_section, content))

            current_section = normalize_section_name(line.strip())
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section.
    content = "\n".join(current_lines).strip()
    if content and not should_skip_section(current_section):
        sections.append((current_section, content))

    # Return empty list when no headings were found so that chunk_text can
    # detect this and apply the fallback path with fallback_used=True.
    if not heading_found:
        return []

    return sections


# ── Paragraph merging ─────────────────────────────────────────────────────────


def _merge_short_paragraphs(paragraphs: list[str]) -> list[str]:
    """
    Merge consecutive paragraphs so that no unit is shorter than MIN_PARAGRAPH_TOKENS.

    Why: a paragraph of 20 tokens produces a nearly-empty embedding vector that
    carries little retrieval signal. Merging it with its neighbour preserves
    context while keeping the chunk count manageable.

    Algorithm: iterate forward; if the current unit is too short, concatenate
    it with the next one before evaluating the result again.
    """
    if not paragraphs:
        return []

    merged: list[str] = []
    buffer = paragraphs[0]

    for para in paragraphs[1:]:
        if count_tokens(buffer) < MIN_PARAGRAPH_TOKENS:
            # Current buffer is too short — absorb the next paragraph.
            buffer = buffer + "\n\n" + para
        else:
            merged.append(buffer)
            buffer = para

    merged.append(buffer)
    return merged


# ── Per-section chunking ──────────────────────────────────────────────────────


def _chunk_section(
    section_text: str,
    section_name: str,
    doi: str,
    evidence_type: str,
    index_offset: int,
) -> list[ChunkMetadata]:
    """
    Split one section's text into token-bounded chunks and tag each with metadata.

    Args:
        section_text:  The cleaned text belonging to this section.
        section_name:  Normalised section name (e.g. "results").
        doi:           Paper DOI — written into every chunk's metadata.
        evidence_type: "FULL_TEXT" or "ABSTRACT".
        index_offset:  The global chunk index where this section starts, so
                       chunk_index values are unique across the whole paper.

    Returns:
        List of ChunkMetadata objects ready for the embedder.
    """
    priority = SECTION_WEIGHTS.get(section_name, SECTION_WEIGHTS["unknown"])
    doi_slug = _doi_to_id(doi)

    # Split section into paragraphs (double newline = paragraph break).
    raw_paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]

    # Merge paragraphs that are too short before splitting.
    units = _merge_short_paragraphs(raw_paragraphs)

    raw_chunks: list[str] = []
    for unit in units:
        if count_tokens(unit) <= TARGET_CHUNK_SIZE:
            raw_chunks.append(unit)
        else:
            # Unit exceeds token limit — apply RecursiveCharacterTextSplitter.
            raw_chunks.extend(_splitter.split_text(unit))

    chunks: list[ChunkMetadata] = []
    for i, text in enumerate(raw_chunks):
        global_index = index_offset + i
        chunks.append(
            ChunkMetadata(
                chunk_id=f"{doi_slug}_chunk_{global_index:03d}",
                section=section_name,
                priority=priority,
                chunk_index=global_index,
                paper_doi=doi,
                evidence_type=evidence_type,
                chunk_text=text,
                token_count=count_tokens(text),
            )
        )

    return chunks


# ── Public API ────────────────────────────────────────────────────────────────


def chunk_text(input_data: ChunkerInput) -> ChunkerOutput:
    """
    Convert clean source text into a list of labelled, token-bounded chunks.

    Args:
        input_data: ChunkerInput containing clean text, DOI, and evidence availability.

    Returns:
        ChunkerOutput with all chunks, section stats, and a fallback flag.
    """
    ev_type = _evidence_type(input_data.evidence_availability)
    doi = input_data.doi

    sections = split_into_sections(input_data.clean_text)
    fallback_used = False

    if not sections:
        # No headings found — chunk the entire text as "unknown".
        logger.warning(
            "DOI %s — no sections detected; applying fallback blind chunking.", doi
        )
        sections = [("unknown", input_data.clean_text.strip())]
        fallback_used = True

    all_chunks: list[ChunkMetadata] = []
    index_offset = 0

    for section_name, section_text in sections:
        new_chunks = _chunk_section(
            section_text=section_text,
            section_name=section_name,
            doi=doi,
            evidence_type=ev_type,
            index_offset=index_offset,
        )
        all_chunks.extend(new_chunks)
        index_offset += len(new_chunks)

    sections_found = list(dict.fromkeys(name for name, _ in sections))  # preserve order, dedupe

    logger.info(
        "DOI %s — produced %d chunks across %d section(s): %s",
        doi,
        len(all_chunks),
        len(sections_found),
        sections_found,
    )

    return ChunkerOutput(
        doi=doi,
        chunks=all_chunks,
        total_chunks=len(all_chunks),
        sections_found=sections_found,
        fallback_used=fallback_used,
    )
