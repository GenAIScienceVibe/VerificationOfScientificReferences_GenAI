from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.models import Reference
from app.models.enums import MappingStatus

YEAR_RE = re.compile(r"\b((?:19|20)\d{2})(?:[a-z])?\b")


@dataclass(frozen=True)
class MappingCandidate:
    reference_id: str | None
    mapping_status: str
    mapping_confidence: float
    mapping_reason: str


class CitationReferenceMapper:
    """Deterministic BE-6 citation-to-reference mapper."""

    def map_citation(self, citation_text: str, references: list[Reference]) -> list[MappingCandidate]:
        citation_text = citation_text.strip()
        if self._is_numbered(citation_text):
            return self._map_numbered(citation_text, references)
        return self._map_author_year(citation_text, references)

    def _is_numbered(self, citation_text: str) -> bool:
        return bool(re.fullmatch(r"\[\d{1,3}(?:\s*(?:,|-|–)\s*\d{1,3})*\]|\(\d{1,3}(?:\s*(?:,|-|–)\s*\d{1,3})*\)|\^\d{1,3}", citation_text))

    def _map_numbered(self, citation_text: str, references: list[Reference]) -> list[MappingCandidate]:
        numbers = self._expand_numbers(citation_text)
        if not numbers:
            return [MappingCandidate(None, MappingStatus.UNCERTAIN.value, 0.0, "Could not parse numeric citation.")]
        mapped: list[MappingCandidate] = []
        for number in numbers:
            index = number - 1
            if 0 <= index < len(references):
                mapped.append(MappingCandidate(references[index].id, MappingStatus.MAPPED.value, 0.95, f"Numeric citation [{number}] mapped by reference order."))
            else:
                mapped.append(MappingCandidate(None, MappingStatus.NO_MATCH.value, 0.0, f"Numeric citation [{number}] is outside the reference list range."))
        return mapped

    def _expand_numbers(self, citation_text: str) -> list[int]:
        text = citation_text.strip().strip("[]()^")
        text = text.replace("–", "-")
        values: list[int] = []
        for part in re.split(r"\s*,\s*", text):
            if "-" in part:
                start_raw, end_raw = [p.strip() for p in part.split("-", 1)]
                if start_raw.isdigit() and end_raw.isdigit():
                    start, end = int(start_raw), int(end_raw)
                    if start <= end and end - start <= 25:
                        values.extend(range(start, end + 1))
            elif part.strip().isdigit():
                values.append(int(part.strip()))
        return values

    def _map_author_year(self, citation_text: str, references: list[Reference]) -> list[MappingCandidate]:
        citation_parts = self._split_author_year_citation(citation_text)
        results: list[MappingCandidate] = []
        for surname, year in citation_parts:
            candidates = self._find_reference_candidates(surname, year, references)
            if len(candidates) == 1:
                results.append(MappingCandidate(candidates[0].id, MappingStatus.MAPPED.value, 0.88, f"Author surname '{surname}' and year '{year}' matched one reference."))
            elif len(candidates) > 1:
                for candidate in candidates:
                    results.append(MappingCandidate(candidate.id, MappingStatus.MULTIPLE_MATCHES.value, 0.55, f"Author surname '{surname}' and year '{year}' matched multiple references."))
            else:
                results.append(MappingCandidate(None, MappingStatus.NO_MATCH.value, 0.0, f"No reference matched author surname '{surname}' and year '{year}'."))
        return self._dedupe_results(results) or [MappingCandidate(None, MappingStatus.UNCERTAIN.value, 0.0, "Could not parse author-year citation.")]

    def _dedupe_results(self, results: list[MappingCandidate]) -> list[MappingCandidate]:
        deduped: list[MappingCandidate] = []
        seen: set[tuple[str | None, str]] = set()
        for item in results:
            key = (item.reference_id, item.mapping_status)
            if key not in seen:
                deduped.append(item)
                seen.add(key)
        return deduped

    def _split_author_year_citation(self, citation_text: str) -> list[tuple[str, int]]:
        text = citation_text.strip()
        narrative = re.match(r"^([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)(?:\s+(?:and|&)\s+([A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)|\s+et\s+al\.)?\s*\(((?:19|20)\d{2})[a-z]?\)$", text)
        if narrative:
            surnames = [narrative.group(1)]
            if narrative.group(2):
                surnames.append(narrative.group(2))
            year = int(narrative.group(3))
            return [(surname, year) for surname in surnames]
        text = text.strip("()")
        parts = [part.strip() for part in text.split(";") if part.strip()]
        parsed: list[tuple[str, int]] = []
        for part in parts:
            year_match = YEAR_RE.search(part)
            if not year_match:
                continue
            year = int(year_match.group(1))
            before_year = part[: year_match.start()].strip(" ,")
            if "&" in before_year:
                surnames = [item.strip().split()[-1] for item in before_year.split("&") if item.strip()]
            elif " and " in before_year:
                surnames = [item.strip().split()[-1] for item in before_year.split(" and ") if item.strip()]
            else:
                surname = before_year.split(",")[0].strip().split()[0] if before_year else ""
                surnames = [surname]
            for surname in surnames:
                if surname:
                    parsed.append((surname, year))
        return parsed

    def _find_reference_candidates(self, surname: str, year: int, references: Iterable[Reference]) -> list[Reference]:
        surname_l = surname.lower()
        matches: list[Reference] = []
        for reference in references:
            if reference.extracted_year and int(reference.extracted_year) != int(year):
                continue
            haystack = " ".join(
                str(part or "")
                for part in (reference.reference_key, reference.extracted_authors, reference.raw_reference, reference.extracted_title)
            ).lower()
            metadata_text = " ".join(
                str(part or "")
                for metadata in getattr(reference, "metadata_records", [])
                for part in (metadata.authors, metadata.title, metadata.year)
            ).lower()
            if surname_l in haystack or surname_l in metadata_text:
                matches.append(reference)
        return matches
