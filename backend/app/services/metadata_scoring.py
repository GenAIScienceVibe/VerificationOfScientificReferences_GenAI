from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class MetadataMatchDetails:
    title_match: float | None
    author_match: float | None
    year_match: bool | None
    doi_match: bool | None
    metadata_match_score: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "title_match": self.title_match,
            "author_match": self.author_match,
            "year_match": self.year_match,
            "doi_match": self.doi_match,
            "metadata_match_score": self.metadata_match_score,
        }


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _token_overlap(left: str | None, right: str | None) -> float | None:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return None
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return None
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return round(max(overlap, sequence), 4)


def _author_score(extracted_authors: str | None, metadata_authors: list[str] | None) -> float | None:
    if not extracted_authors or not metadata_authors:
        return None
    extracted = _normalize_text(extracted_authors)
    if not extracted:
        return None
    author_text = _normalize_text(" ".join(metadata_authors))
    if not author_text:
        return None
    # Surnames often survive PDF/reference parsing better than full names.
    metadata_surnames = []
    for author in metadata_authors:
        parts = _normalize_text(author).split()
        if parts:
            metadata_surnames.append(parts[-1])
    if metadata_surnames:
        hits = sum(1 for surname in metadata_surnames if surname in extracted)
        surname_score = hits / len(metadata_surnames)
    else:
        surname_score = 0.0
    full_text_score = _token_overlap(extracted, author_text) or 0.0
    return round(max(surname_score, full_text_score), 4)


def calculate_metadata_match(
    *,
    extracted_title: str | None,
    extracted_authors: str | None,
    extracted_year: int | None,
    extracted_doi: str | None,
    metadata_title: str | None,
    metadata_authors: list[str] | None,
    metadata_year: int | None,
    metadata_doi: str | None,
) -> MetadataMatchDetails:
    title_match = _token_overlap(extracted_title, metadata_title)
    author_match = _author_score(extracted_authors, metadata_authors)
    year_match = None
    if extracted_year is not None and metadata_year is not None:
        year_match = extracted_year == metadata_year
    doi_match = None
    if extracted_doi and metadata_doi:
        doi_match = extracted_doi.strip().lower() == metadata_doi.strip().lower()

    weighted: list[tuple[float, float]] = []
    if title_match is not None:
        weighted.append((0.40, title_match))
    if author_match is not None:
        weighted.append((0.25, author_match))
    if year_match is not None:
        weighted.append((0.20, 1.0 if year_match else 0.0))
    if doi_match is not None:
        weighted.append((0.15, 1.0 if doi_match else 0.0))

    if not weighted:
        score = None
    else:
        total_weight = sum(weight for weight, _ in weighted)
        score = round(sum(weight * value for weight, value in weighted) / total_weight, 4)

    return MetadataMatchDetails(
        title_match=title_match,
        author_match=author_match,
        year_match=year_match,
        doi_match=doi_match,
        metadata_match_score=score,
    )
