from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectedSection:
    name: str
    order_index: int
    text: str
    text_preview: str
    page_start: int | None = None
    page_end: int | None = None


REFERENCE_HEADINGS = {
    "references",
    "bibliography",
    "works cited",
    "reference list",
    "literatur",
    "literaturverzeichnis",
}

POST_REFERENCE_STOP_HEADINGS = {
    "appendix",
    "appendices",
    "supplementary material",
    "supplemental material",
    "acknowledgement",
    "acknowledgements",
    "acknowledgment",
    "acknowledgments",
    "survey",
    "questionnaire",
    "screenout",
    "last page",
    "consent",
    "demographic questions",
    "ai tool usage",
    "employment status",
}

BODY_HEADINGS = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "background": "Body",
    "method": "Methods",
    "methods": "Methods",
    "methodology": "Methods",
    "results": "Results",
    "result": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}

HEADING_WORDS = set(BODY_HEADINGS) | REFERENCE_HEADINGS | POST_REFERENCE_STOP_HEADINGS

PDF_ARTIFACT_PATTERNS = [
    re.compile(r"^\s*TEPIAN\s+Vol\.", re.IGNORECASE),
    re.compile(r"^\s*[pe]-ISSN\b", re.IGNORECASE),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,4}\s*$"),
    re.compile(r"^\s*[–—-]\s*\d+\s*[–—-]\s*$"),
    re.compile(r"^\s*https?://journalpedia\.com/?\s*$", re.IGNORECASE),
    re.compile(r"^\s*https?://journalpedia\.com/1/index\.php/jsti/?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{2}\.\d{2}\.\d{4},\s*\d{2}:\d{2}\s+test\d+\s*→\s*base\s+Page", re.IGNORECASE),
    re.compile(r"^\s*test\d+\s*→\s*base\s+Page", re.IGNORECASE),
]

TOC_LINE_REGEX = re.compile(r"^\s*(?:\d+(?:\.\d+)*\s+)?[A-Za-z][A-Za-z\s]{2,80}\s*(?:\.{2,}|\s{3,})\s*\d+\s*$")


def _line_key(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).lower()


def _heading_key(line: str) -> str | None:
    cleaned = re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", line.strip())
    cleaned = cleaned.strip(" .:\t").lower()
    return cleaned or None


def is_toc_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if TOC_LINE_REGEX.match(stripped):
        return True
    # Example: "References 15" near a table of contents.
    return bool(re.match(r"^(references|bibliography|appendix|appendix\s+[a-z])\s+\d{1,3}$", stripped, re.IGNORECASE))


def is_probable_heading_line(line: str) -> bool:
    if is_toc_heading_line(line):
        return False
    key = _heading_key(line)
    if not key:
        return False
    if key in HEADING_WORDS:
        return True
    return bool(re.fullmatch(r"appendix\s+[a-z]", key))


def is_reference_heading_line(line: str) -> bool:
    return (_heading_key(line) or "") in REFERENCE_HEADINGS and not is_toc_heading_line(line)


def is_post_reference_stop_heading_line(line: str) -> bool:
    key = _heading_key(line) or ""
    if key in POST_REFERENCE_STOP_HEADINGS:
        return True
    if re.fullmatch(r"appendix\s+[a-z]", key) or re.match(r"appendix\s+[a-z]\b", key):
        return True
    # Survey export pages are not always formatted as clean headings.
    stripped = line.strip().lower()
    return any(
        marker in stripped
        for marker in (
            "welcome to the study",
            "employment status",
            "demographic questions",
            "ai tool usage",
            "screenout",
            "last page",
            "test510",
            "base page 01",
        )
    )


def is_probable_pdf_artifact_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in PDF_ARTIFACT_PATTERNS)


def _looks_like_author_start_fragment(token: str) -> bool:
    fragment = token.strip()
    return bool(
        re.match(r"^[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+\s*,\s*(?:[A-Z]\.|[A-Z][a-z]+)", fragment)
        or re.match(r"^[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+\s+(?:[A-Z]\.|[A-Z][a-z]+)", fragment)
    )


def _is_safe_doi_continuation_token(token: str) -> bool:
    fragment = token.strip().strip("<>")
    if not fragment:
        return False
    if _looks_like_author_start_fragment(fragment):
        return False
    # Most true DOI continuations after a PDF line break begin with digits, lower-case
    # DOI path characters, or a DOI path separator. Capitalized author surnames must
    # not be joined into the DOI.
    return bool(re.match(r"^(?:[0-9]|[a-z]|[._/;:()])[-._;()/:+A-Za-z0-9]*", fragment))


def repair_doi_line_continuations(text: str) -> str:
    """Repair common PDF line breaks inside DOI strings before extraction.

    The repair is intentionally conservative. It joins DOI prefixes and DOI body
    continuations, but refuses to join the next line when it looks like the next
    reference's author name, preventing results such as
    ``10.1146/annurev-psych-120710-preacher``.
    """
    repaired = text.replace("\r\n", "\n").replace("\r", "\n")
    repaired = re.sub(
        r"(?i)(https?://(?:dx\.)?doi\.org/)[ \t]*\n[ \t]*(10\.)",
        r"\1\2",
        repaired,
    )
    repaired = re.sub(r"(?i)(\bdoi\s*[: ]\s*)[ \t]*\n[ \t]*(10\.)", r"\1\2", repaired)

    doi_continuation = re.compile(
        r"(?i)(10\.\d{4,9}/[A-Z0-9][A-Z0-9._;()/:+-]*[-/:;.])[ \t]*\n[ \t]*([^\n\s][^\n]*)"
    )

    def join_if_safe(match: re.Match[str]) -> str:
        prefix = match.group(1)
        following_line = match.group(2).strip()
        if re.match(r"^(?:\[\d+\]|\d+[.)])\s+[A-ZÀ-Þ]", following_line):
            return f"{prefix}\n{following_line}"
        first_token = following_line.split()[0].strip() if following_line.split() else following_line
        if _is_safe_doi_continuation_token(first_token):
            return f"{prefix}{following_line}"
        return f"{prefix}\n{following_line}"

    previous = None
    while previous != repaired:
        previous = repaired
        repaired = doi_continuation.sub(join_if_safe, repaired)
    return repaired


def normalize_pdf_line_breaks(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    for line in lines:
        current = line.rstrip()
        if not output:
            output.append(current)
            continue
        prev = output[-1]
        prev_key = _heading_key(prev) or ""
        curr_key = _heading_key(current) or ""
        should_join = (
            prev
            and current
            and prev_key not in HEADING_WORDS
            and curr_key not in HEADING_WORDS
            and not is_toc_heading_line(prev)
            and not is_toc_heading_line(current)
            and not re.search(r"[.!?)]\s*$", prev)
            and not re.match(r"^(?:\[\d+\]|\d+[.)])\s+", current)
            and re.search(r"[a-z,;:]$", prev)
            and re.match(r"^[a-z(]", current)
        )
        if should_join:
            output[-1] = f"{prev} {current.strip()}"
        else:
            output.append(current)
    return "\n".join(output)


def remove_repeated_page_artifacts_from_pages(page_texts: list[str]) -> list[str]:
    if not page_texts:
        return []
    if len(page_texts) < 2:
        return [remove_repeated_page_artifacts(page) for page in page_texts]
    candidates: list[str] = []
    for page in page_texts:
        lines = [line.strip() for line in page.replace("\r", "\n").split("\n") if line.strip()]
        # Use a set per page so overlapping first-5/last-5 on short pages doesn't
        # double-count legitimate content lines and falsely mark them as repeated artifacts.
        page_candidates: set[str] = set()
        page_candidates.update(_line_key(line) for line in lines[:5])
        page_candidates.update(_line_key(line) for line in lines[-5:])
        candidates.extend(page_candidates)
    counts = Counter(candidates)
    repeated = {key for key, count in counts.items() if count >= 2 and len(key) >= 5}

    cleaned_pages: list[str] = []
    for page in page_texts:
        kept: list[str] = []
        for line in page.replace("\r", "\n").split("\n"):
            key = _line_key(line)
            if key in repeated or is_probable_pdf_artifact_line(line):
                continue
            kept.append(line)
        cleaned_pages.append("\n".join(kept))
    return cleaned_pages


def remove_repeated_page_artifacts(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not is_probable_pdf_artifact_line(line))


def clean_text(raw_text: str) -> str:
    """Clean extracted/submitted text without destroying citations, DOI strings, or reference lines."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = repair_doi_line_continuations(text)
    text = remove_repeated_page_artifacts(text)
    # Collapse horizontal whitespace but keep line breaks for headings/paragraphs.
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = normalize_pdf_line_breaks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pdf_pages(page_texts: list[str]) -> str:
    cleaned_pages = remove_repeated_page_artifacts_from_pages(page_texts)
    return clean_text("\n\n".join(cleaned_pages))


def _preview(text: str, limit: int = 500) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit]


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:512]
    return None


def _heading_name(key: str) -> str:
    if key in REFERENCE_HEADINGS:
        return "References"
    if key in BODY_HEADINGS:
        return BODY_HEADINGS[key]
    if key.startswith("appendix"):
        return "Appendix"
    return key.title()


def _find_heading_matches(text: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    offset = 0
    total_len = len(text)
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.strip()
        line_start = offset
        line_end = offset + len(raw_line)
        offset = line_end
        if not line:
            continue
        key = _heading_key(line)
        if not key:
            continue
        # Avoid table-of-contents entries and early References page markers.
        if is_toc_heading_line(line):
            continue
        if (
            key in BODY_HEADINGS
            or key in REFERENCE_HEADINGS
            or key in POST_REFERENCE_STOP_HEADINGS
            or re.fullmatch(r"appendix\s+[a-z]", key)
            or re.match(r"appendix\s+[a-z]\b", key)
        ):
            # Prefer actual body headings over ToC-like headings in the first 20%.
            if key in REFERENCE_HEADINGS and line_start < total_len * 0.20:
                nearby = text[max(0, line_start - 800) : min(total_len, line_end + 800)]
                if re.search(r"\.{2,}\s*\d+", nearby) or re.search(r"table\s+of\s+contents", nearby, re.IGNORECASE):
                    continue
            matches.append((key, line_start, line_end))
    return matches


def _add_section(sections: list[DetectedSection], name: str, text: str) -> None:
    content = text.strip()
    if not content:
        return
    # Avoid duplicate title/body slivers.
    if len(content) < 3:
        return
    sections.append(
        DetectedSection(
            name=name,
            order_index=len(sections),
            text=content,
            text_preview=_preview(content),
        )
    )


def detect_basic_sections(cleaned_text: str) -> list[DetectedSection]:
    """Rule-based BE-3 section detector hardened for references boundaries.

    This intentionally does not split individual references or extract citations/DOIs.
    It only stores broad sections for BE-4 and later phases to consume.
    """
    text = cleaned_text.strip()
    if not text:
        return []

    matches = _find_heading_matches(text)
    sections: list[DetectedSection] = []

    first_heading_start = matches[0][1] if matches else len(text)
    title_candidate = _first_non_empty_line(text[:first_heading_start]) or _first_non_empty_line(text)
    if title_candidate:
        _add_section(sections, "Title", title_candidate)

    if not matches:
        _add_section(sections, "Body", text)
        return sections

    # Prefer the last real References/Bibliography heading. Ignore anything after References except stop headings.
    reference_indexes = [idx for idx, (key, _, _) in enumerate(matches) if key in REFERENCE_HEADINGS]
    terminal_reference_index = reference_indexes[-1] if reference_indexes else None
    effective_matches = matches[: terminal_reference_index + 1] if terminal_reference_index is not None else matches

    # Preface/body before first heading.
    preface = text[: effective_matches[0][1]].strip()
    if preface and preface != title_candidate and len(preface) > len(title_candidate or "") + 20:
        _add_section(sections, "Body", preface)

    for index, (key, _start, end) in enumerate(effective_matches):
        content_start = end
        if key in REFERENCE_HEADINGS:
            # References continue until a post-reference stop heading or EOF.
            content_end = len(text)
            for stop_key, stop_start, _ in matches[index + 1 :]:
                if stop_key in POST_REFERENCE_STOP_HEADINGS or re.fullmatch(r"appendix\s+[a-z]", stop_key) or re.match(r"appendix\s+[a-z]\b", stop_key):
                    content_end = stop_start
                    break
            _add_section(sections, "References", text[content_start:content_end])
            break
        content_end = effective_matches[index + 1][1] if index + 1 < len(effective_matches) else len(text)
        normalized_name = _heading_name(key)
        if normalized_name == "Appendix":
            continue
        _add_section(sections, normalized_name, text[content_start:content_end])

    if not any(section.name != "Title" for section in sections):
        _add_section(sections, "Body", text)

    return [
        DetectedSection(
            name=section.name,
            order_index=index,
            text=section.text,
            text_preview=section.text_preview,
            page_start=section.page_start,
            page_end=section.page_end,
        )
        for index, section in enumerate(sections)
    ]
