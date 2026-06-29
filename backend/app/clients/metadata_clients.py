from __future__ import annotations

import difflib
import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.models.enums import MetadataStatus


@dataclass(frozen=True)
class MetadataLookupResponse:
    success: bool
    lookup_source: str
    lookup_status: str
    doi: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    abstract: str | None = None
    url: str | None = None
    raw_metadata_json: dict[str, Any] | None = None
    status_code: int | None = None
    error_code: str | None = None
    error_message: str | None = None


def _first_string(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return _first_string(value[0])
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _extract_year(message: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = message.get(key, {}).get("date-parts") if isinstance(message.get(key), dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def _extract_authors(message: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in message.get("author") or []:
        if not isinstance(author, dict):
            continue
        family = str(author.get("family") or "").strip()
        given = str(author.get("given") or "").strip()
        literal = str(author.get("name") or "").strip()
        if family and given:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
        elif literal:
            authors.append(literal)
    return authors


def _clean_abstract(value: Any) -> str | None:
    text = _first_string(value)
    if not text:
        return None
    # CrossRef sometimes returns very small JATS/HTML snippets.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _normalize_title(title: str) -> str:
    """Lowercase, decode HTML entities, strip punctuation, collapse whitespace."""
    title = html.unescape(title)  # &amp; → &, &quot; → ", etc. (CrossRef encodes &)
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _title_matches(ref_title: str, result_title: str) -> bool:
    """Return True if the normalized reference title is an exact match or exact
    substring of the normalized result title (handles main-title-without-subtitle),
    OR if character-level similarity is >= 0.98 (allows 1-2 character OCR errors).

    Deliberately strict: a single swapped keyword fails this check. False-match
    prevention is the priority — it is better to fall back to NEEDS_HUMAN_REVIEW
    than to verify a claim against the wrong paper.
    """
    if not ref_title or not result_title:
        return False
    na = _normalize_title(ref_title)
    nb = _normalize_title(result_title)
    # Exact equality or one is contained in the other (subtitle case)
    if na == nb or na in nb or nb in na:
        return True
    # Tight fuzzy fallback for 1-2 character OCR errors only
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.98


def _first_author_matches(reference_authors_str: str, result_authors: list[str]) -> bool:
    """Return True if the first author's last name from the reference appears in
    any of the result's author names.

    Using the first author (not any author) is intentional: last names like
    'Smith' or 'Wang' are common, so matching against any author in a list would
    produce too many false positives. The first author is the primary citation
    identifier in bibliographic practice.

    Returns True (i.e. does not block) when either side has no author data.
    """
    if not reference_authors_str or not reference_authors_str.strip() or not result_authors:
        return True  # no data to check — do not block on absence of info

    # Take the first semicolon-separated author entry
    first_entry = re.split(r";", reference_authors_str.strip())[0].strip()
    if not first_entry:
        return True

    # Determine last name: "Zhu, David H." -> "zhu" | "David H. Zhu" -> "zhu"
    if "," in first_entry:
        last_name = first_entry.split(",")[0].strip().lower()
    else:
        tokens = first_entry.split()
        last_name = tokens[-1].lower() if tokens else ""

    if not last_name:
        return True

    return any(last_name in name.lower() for name in result_authors)


class CrossrefClient:
    """Small CrossRef DOI metadata client used by BE-5.

    The client only sends DOI values to CrossRef. It never sends uploaded document
    text, reference sections, or claim content.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.crossref_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def lookup_by_doi(self, doi: str) -> MetadataLookupResponse:
        headers = {"User-Agent": self.settings.metadata_user_agent}
        params: dict[str, str] = {}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        encoded_doi = doi.strip()
        url = f"{self.base_url}/works/{encoded_doi}"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                error_code="METADATA_LOOKUP_TIMEOUT",
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                error_code="METADATA_SERVICE_UNAVAILABLE",
                error_message=str(exc),
            )

        if response.status_code == 404:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                doi=doi,
                status_code=response.status_code,
                error_code="METADATA_UNAVAILABLE",
                error_message="CrossRef did not find metadata for this DOI.",
            )
        if response.status_code >= 400:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned HTTP {response.status_code}.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned malformed JSON: {exc}",
            )

        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message="CrossRef response did not contain a message object.",
                raw_metadata_json=payload if isinstance(payload, dict) else None,
            )

        return MetadataLookupResponse(
            success=True,
            lookup_source="CrossRef",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=str(message.get("DOI") or doi).lower(),
            title=_first_string(message.get("title")),
            authors=_extract_authors(message),
            year=_extract_year(message),
            venue=_first_string(message.get("container-title") or message.get("short-container-title")),
            publisher=_first_string(message.get("publisher")),
            abstract=_clean_abstract(message.get("abstract")),
            url=_first_string(message.get("URL")) or f"https://doi.org/{doi}",
            raw_metadata_json=payload,
            status_code=response.status_code,
        )


    def search_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> MetadataLookupResponse:
        """Search CrossRef for a paper by title using the bibliographic query endpoint.

        CrossRef's polite pool (enabled by the mailto setting) allows high throughput
        with no meaningful rate limit, making it the preferred first stop in the
        title-based DOI resolution chain.

        The same three false-match gates as SemanticScholarClient.search_by_title()
        are applied: title exact/substring match, year ±1, first-author last name.
        """
        params: dict[str, str] = {
            "query.bibliographic": title.strip(),
            "rows": "5",
            "sort": "score",
            "order": "desc",
        }
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        headers = {"User-Agent": self.settings.metadata_user_agent}
        url = f"{self.base_url}/works"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code != 200:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.LOOKUP_FAILED.value, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"CrossRef search returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="DOI_LOOKUP_FAILED", error_message=f"Malformed JSON: {exc}")

        items = (payload.get("message") or {}).get("items") or []
        if not items:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="METADATA_UNAVAILABLE", error_message="CrossRef title search returned no results.")

        for item in items:
            result_title = _first_string(item.get("title")) or ""
            if not _title_matches(title, result_title):
                continue
            result_year = _extract_year(item)
            if year is not None and result_year is not None and abs(year - result_year) > 1:
                continue
            result_authors = _extract_authors(item)
            if authors and result_authors and not _first_author_matches(authors, result_authors):
                continue
            # All gates passed
            found_doi = str(item.get("DOI") or "").lower().strip() or None
            url_field = _first_string(item.get("URL")) or (f"https://doi.org/{found_doi}" if found_doi else None)
            return MetadataLookupResponse(
                success=True,
                lookup_source="CrossRef-TitleSearch",
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                doi=found_doi,
                title=result_title or None,
                authors=result_authors or None,
                year=result_year,
                venue=_first_string(item.get("container-title") or item.get("short-container-title")),
                publisher=_first_string(item.get("publisher")),
                abstract=_clean_abstract(item.get("abstract")),
                url=url_field,
                raw_metadata_json=item,
                status_code=response.status_code,
            )

        return MetadataLookupResponse(success=False, lookup_source="CrossRef", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="TITLE_MATCH_INSUFFICIENT", error_message=f"No CrossRef result passed title/author/year gates for query '{title[:80]}'.")

    def lookup_by_isbn(self, isbn: str) -> MetadataLookupResponse:
        """Look up a book by ISBN via CrossRef's filter endpoint.

        CrossRef indexes many books with ISBNs even when no DOI is assigned to
        journal articles — this is the most reliable way to find DOIs for textbooks
        like 'Hayes (2018)' that are cited without a DOI in APA bibliographies.

        Args:
            isbn: ISBN-10 or ISBN-13 (hyphens and spaces are stripped automatically).

        Returns:
            MetadataLookupResponse with DOI and metadata when found, success=False otherwise.
        """
        isbn_clean = re.sub(r"[-\s]", "", isbn)
        params: dict[str, str] = {"filter": f"isbn:{isbn_clean}", "rows": "3"}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        headers = {"User-Agent": self.settings.metadata_user_agent}
        url = f"{self.base_url}/works"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef-ISBN", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef-ISBN", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code != 200:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef-ISBN", lookup_status=MetadataStatus.LOOKUP_FAILED.value, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"CrossRef ISBN search returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef-ISBN", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="DOI_LOOKUP_FAILED", error_message=f"Malformed JSON: {exc}")

        items = (payload.get("message") or {}).get("items") or []
        if not items:
            return MetadataLookupResponse(success=False, lookup_source="CrossRef-ISBN", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="METADATA_UNAVAILABLE", error_message=f"CrossRef found no record for ISBN {isbn_clean}.")

        item = items[0]
        found_doi = str(item.get("DOI") or "").lower().strip() or None
        url_field = _first_string(item.get("URL")) or (f"https://doi.org/{found_doi}" if found_doi else None)
        return MetadataLookupResponse(
            success=True,
            lookup_source="CrossRef-ISBN",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=found_doi,
            title=_first_string(item.get("title")),
            authors=_extract_authors(item),
            year=_extract_year(item),
            venue=_first_string(item.get("container-title") or item.get("short-container-title")),
            publisher=_first_string(item.get("publisher")),
            abstract=_clean_abstract(item.get("abstract")),
            url=url_field,
            raw_metadata_json=item,
            status_code=response.status_code,
        )


class OpenAlexClient:
    """OpenAlex abstract/open-access fallback client used by BE-5.

    Called only when CrossRef returns no abstract. Sends only the normalized
    DOI — no document text, no claim content.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.openalex_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def lookup_by_doi(self, doi: str) -> MetadataLookupResponse:
        url = f"{self.base_url}/works/doi:{doi}"
        params: dict[str, str] = {}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        headers = {"User-Agent": self.settings.metadata_user_agent}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code == 404:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, doi=doi, status_code=response.status_code, error_code="METADATA_UNAVAILABLE", error_message="OpenAlex did not find metadata for this DOI.")
        if response.status_code >= 400:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"OpenAlex returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"OpenAlex returned malformed JSON: {exc}")

        if not isinstance(payload, dict):
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="DOI_LOOKUP_FAILED", error_message="OpenAlex response was not a JSON object.")

        abstract = _reconstruct_openalex_abstract(payload.get("abstract_inverted_index"))

        authorships = payload.get("authorships") or []
        authors = [
            str(a.get("author", {}).get("display_name", "")).strip()
            for a in authorships
            if isinstance(a, dict) and isinstance(a.get("author"), dict) and a["author"].get("display_name")
        ]

        primary_location = payload.get("primary_location") or {}
        source = primary_location.get("source") if isinstance(primary_location, dict) else None
        venue = source.get("display_name") if isinstance(source, dict) else None

        best_oa = payload.get("best_oa_location") or {}
        oa_url = (best_oa.get("pdf_url") or best_oa.get("landing_page_url")) if isinstance(best_oa, dict) else None

        raw_doi = str(payload.get("doi") or doi).lower()
        for prefix in ("https://doi.org/", "http://doi.org/"):
            if raw_doi.startswith(prefix):
                raw_doi = raw_doi[len(prefix):]

        return MetadataLookupResponse(
            success=True,
            lookup_source="OpenAlex",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=raw_doi,
            title=_first_string(payload.get("title")),
            authors=authors or None,
            year=payload.get("publication_year"),
            venue=venue,
            publisher=None,
            abstract=abstract,
            url=oa_url or f"https://doi.org/{doi}",
            raw_metadata_json=payload,
            status_code=response.status_code,
        )


    def search_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> MetadataLookupResponse:
        """Search OpenAlex for a paper by title.

        OpenAlex has generous rate limits (no hard cap with polite mailto) making
        it a reliable second step in the title-based DOI resolution chain when
        CrossRef finds no match.
        """
        params: dict[str, str] = {"search": title.strip(), "per-page": "5"}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        headers = {"User-Agent": self.settings.metadata_user_agent}
        url = f"{self.base_url}/works"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code != 200:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"OpenAlex search returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="DOI_LOOKUP_FAILED", error_message=f"Malformed JSON: {exc}")

        results = payload.get("results") or []
        if not results:
            return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="METADATA_UNAVAILABLE", error_message="OpenAlex title search returned no results.")

        for item in results:
            result_title = _first_string(item.get("title")) or ""
            if not _title_matches(title, result_title):
                continue
            result_year: int | None = item.get("publication_year")
            if year is not None and result_year is not None and abs(year - result_year) > 1:
                continue
            authorships = item.get("authorships") or []
            result_authors = [
                str(a.get("author", {}).get("display_name", "")).strip()
                for a in authorships
                if isinstance(a, dict) and isinstance(a.get("author"), dict) and a["author"].get("display_name")
            ]
            if authors and result_authors and not _first_author_matches(authors, result_authors):
                continue
            # All gates passed — extract DOI
            raw_doi = str(item.get("doi") or "").lower()
            for prefix in ("https://doi.org/", "http://doi.org/"):
                if raw_doi.startswith(prefix):
                    raw_doi = raw_doi[len(prefix):]
            found_doi = raw_doi or None
            abstract = _reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
            primary_loc = item.get("primary_location") or {}
            source = primary_loc.get("source") if isinstance(primary_loc, dict) else None
            venue = source.get("display_name") if isinstance(source, dict) else None
            best_oa = item.get("best_oa_location") or {}
            oa_url = (best_oa.get("pdf_url") or best_oa.get("landing_page_url")) if isinstance(best_oa, dict) else None
            return MetadataLookupResponse(
                success=True,
                lookup_source="OpenAlex-TitleSearch",
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                doi=found_doi,
                title=result_title or None,
                authors=result_authors or None,
                year=result_year,
                venue=venue,
                publisher=None,
                abstract=abstract,
                url=oa_url or (f"https://doi.org/{found_doi}" if found_doi else None),
                raw_metadata_json=item,
                status_code=response.status_code,
            )

        return MetadataLookupResponse(success=False, lookup_source="OpenAlex", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="TITLE_MATCH_INSUFFICIENT", error_message=f"No OpenAlex result passed title/author/year gates for query '{title[:80]}'.")


class SemanticScholarClient:
    """Semantic Scholar abstract/open-access fallback client used by BE-5.

    Called only when both CrossRef and OpenAlex return no abstract. Sends only
    the normalized DOI — no document text, no claim content.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.semantic_scholar_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def lookup_by_doi(self, doi: str) -> MetadataLookupResponse:
        url = f"{self.base_url}/graph/v1/paper/DOI:{doi}"
        params = {"fields": "title,authors,year,abstract,venue,openAccessPdf"}
        headers = {"User-Agent": self.settings.metadata_user_agent}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code == 404:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, doi=doi, status_code=response.status_code, error_code="METADATA_UNAVAILABLE", error_message="Semantic Scholar did not find this DOI.")
        if response.status_code >= 400:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"Semantic Scholar returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"Semantic Scholar returned malformed JSON: {exc}")

        if not isinstance(payload, dict):
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi, error_code="DOI_LOOKUP_FAILED", error_message="Semantic Scholar response was not a JSON object.")

        authors = [
            str(a.get("name", "")).strip()
            for a in (payload.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]

        oa_pdf = payload.get("openAccessPdf") or {}
        oa_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None

        return MetadataLookupResponse(
            success=True,
            lookup_source="SemanticScholar",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=doi,
            title=_first_string(payload.get("title")),
            authors=authors or None,
            year=payload.get("year"),
            venue=_first_string(payload.get("venue")),
            publisher=None,
            abstract=_first_string(payload.get("abstract")),
            url=oa_url or f"https://doi.org/{doi}",
            raw_metadata_json=payload,
            status_code=response.status_code,
        )

    def lookup_by_arxiv_id(self, arxiv_id: str) -> MetadataLookupResponse:
        """Look up a paper by arXiv ID (e.g. '2109.05581') using the arXiv: prefix."""
        url = f"{self.base_url}/graph/v1/paper/arXiv:{arxiv_id}"
        params = {"fields": "title,authors,year,abstract,venue,openAccessPdf,externalIds"}
        headers = {"User-Agent": self.settings.metadata_user_agent}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=f"10.48550/arXiv.{arxiv_id}", error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=f"10.48550/arXiv.{arxiv_id}", error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code != 200:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=f"10.48550/arXiv.{arxiv_id}", status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"Semantic Scholar returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError:
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=f"10.48550/arXiv.{arxiv_id}", error_code="DOI_LOOKUP_FAILED", error_message="Malformed JSON.")

        if not isinstance(payload, dict):
            return MetadataLookupResponse(success=False, lookup_source="SemanticScholar", lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=f"10.48550/arXiv.{arxiv_id}", error_code="DOI_LOOKUP_FAILED", error_message="Response was not a JSON object.")

        authors = [
            str(a.get("name", "")).strip()
            for a in (payload.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        oa_pdf = payload.get("openAccessPdf") or {}
        oa_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None
        registered_doi = (payload.get("externalIds") or {}).get("DOI") or f"10.48550/arXiv.{arxiv_id}"

        return MetadataLookupResponse(
            success=True,
            lookup_source="SemanticScholar",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=registered_doi,
            title=_first_string(payload.get("title")),
            authors=authors or None,
            year=payload.get("year"),
            venue=_first_string(payload.get("venue")),
            publisher=None,
            abstract=_first_string(payload.get("abstract")),
            url=oa_url or f"https://arxiv.org/abs/{arxiv_id}",
            raw_metadata_json=payload,
            status_code=response.status_code,
        )

    def search_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> MetadataLookupResponse:
        """Search Semantic Scholar for a paper by title and return the best confident match.

        False-match prevention — all three gates must pass:
        1. Title: normalized reference title must equal or be an exact substring of
           the SS result title (handles main-title-without-subtitle). A 0.98 char-ratio
           fallback allows 1-2 OCR errors. A single swapped keyword fails.
        2. Year: must agree within 1 year when both sides have a year.
        3. First author: the first author's last name from the reference must appear
           in the SS result's author list.

        Returns success=False with a descriptive error_code if no confident match is found.
        When success=True, the DOI field is populated from externalIds (or arXiv form as fallback).
        """
        url = f"{self.base_url}/graph/v1/paper/search"
        params: dict[str, str] = {
            "query": title.strip(),
            "fields": "title,authors,year,externalIds,abstract,venue,openAccessPdf",
            "limit": "5",
        }
        headers = {"User-Agent": self.settings.metadata_user_agent}
        # SS /paper/search rate-limits unauthenticated callers at ~5-10 req/min —
        # much stricter than the DOI-lookup endpoints. A 3-second pause keeps us
        # at ~20 req/min; combined with the 5-second 429 retry this stays safe.
        time.sleep(3)
        response = None
        for attempt in range(2):
            try:
                if self._client is not None:
                    response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
                else:
                    with httpx.Client(timeout=self.timeout) as client:
                        response = client.get(url, headers=headers, params=params)
            except httpx.TimeoutException as exc:
                return MetadataLookupResponse(
                    success=False,
                    lookup_source="SemanticScholar",
                    lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                    error_code="METADATA_LOOKUP_TIMEOUT",
                    error_message=str(exc),
                )
            except httpx.HTTPError as exc:
                return MetadataLookupResponse(
                    success=False,
                    lookup_source="SemanticScholar",
                    lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                    error_code="METADATA_SERVICE_UNAVAILABLE",
                    error_message=str(exc),
                )
            if response.status_code == 429 and attempt == 0:
                # Rate-limited: back off for 10 seconds and retry once
                time.sleep(10)
                continue
            break

        if response is None or response.status_code != 200:
            status_code = response.status_code if response is not None else None
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                status_code=status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"Semantic Scholar search returned HTTP {status_code}.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"Malformed JSON from Semantic Scholar search: {exc}",
            )

        if not isinstance(payload, dict):
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="DOI_LOOKUP_FAILED",
                error_message="Semantic Scholar search response was not a JSON object.",
            )

        data = payload.get("data") or []
        if not data:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="METADATA_UNAVAILABLE",
                error_message="Semantic Scholar title search returned no results.",
            )

        best = data[0]  # ranked by SemanticScholar relevance; we check confidence below
        result_title = best.get("title") or ""

        # Gate 1 — title must be an exact match or exact substring after normalization
        # (a single swapped keyword fails; see _title_matches docstring for details)
        if not _title_matches(title, result_title):
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="TITLE_MATCH_INSUFFICIENT",
                error_message=(
                    f"Best match '{result_title}' did not pass title exact-match check "
                    f"(query: '{title[:80]}')."
                ),
            )

        # Gate 2 — year must agree within 1 year (skip if either side has no year)
        result_year: int | None = best.get("year")
        if year is not None and result_year is not None and abs(year - result_year) > 1:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="YEAR_MISMATCH",
                error_message=f"Year mismatch: reference={year}, found={result_year}.",
            )

        # Gate 3 — first author's last name must appear in result's author list
        result_authors_raw: list[str] = [
            str(a.get("name", "")).strip()
            for a in (best.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        if authors and not _first_author_matches(authors, result_authors_raw):
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="AUTHOR_MISMATCH",
                error_message="First author's last name does not appear in search result authors.",
            )

        # Confident match — extract DOI (prefer registered DOI, fall back to arXiv synthetic form)
        external_ids = best.get("externalIds") or {}
        found_doi: str | None = external_ids.get("DOI")
        if not found_doi:
            arxiv_id = external_ids.get("ArXiv")
            found_doi = f"10.48550/arXiv.{arxiv_id}" if arxiv_id else None

        oa_pdf = best.get("openAccessPdf") or {}
        oa_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None

        return MetadataLookupResponse(
            success=True,
            lookup_source="SemanticScholar-TitleSearch",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=found_doi,
            title=result_title or None,
            authors=result_authors_raw or None,
            year=result_year,
            venue=_first_string(best.get("venue")),
            publisher=None,
            abstract=_first_string(best.get("abstract")),
            url=oa_url or (f"https://doi.org/{found_doi}" if found_doi else None),
            raw_metadata_json=best,
            status_code=response.status_code,
        )


class UnpaywallClient:
    """Unpaywall open-access PDF URL client used by BE-5.

    Called only to obtain a PDF download URL when no OA link was returned by
    OpenAlex or Semantic Scholar. Requires UNPAYWALL_EMAIL in settings (free,
    no API key). Sends only the normalized DOI.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.unpaywall_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def lookup_by_doi(self, doi: str) -> str | None:
        """Return the best open-access PDF URL for *doi*, or None."""
        if not self.settings.unpaywall_email:
            return None
        url = f"{self.base_url}/v2/{doi}"
        params = {"email": self.settings.unpaywall_email}
        headers = {"User-Agent": self.settings.metadata_user_agent}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return None
            payload = response.json()
        except Exception:
            return None

        if not isinstance(payload, dict) or not payload.get("is_oa"):
            return None

        best = payload.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf") if isinstance(best, dict) else None
        if pdf_url:
            return pdf_url

        for location in (payload.get("oa_locations") or []):
            if isinstance(location, dict) and location.get("url_for_pdf"):
                return location["url_for_pdf"]
        return None


class CoreClient:
    """CORE API v3 client for full-text retrieval and title-based DOI resolution.

    Used in two roles:
    1. search_by_title() — 4th step in the title-based DOI resolution chain, after
       CrossRef, OpenAlex, and Semantic Scholar. CORE covers institutional repositories
       and preprints not indexed by those sources.
    2. get_fulltext_by_doi() — returns full text directly from the CORE API response
       (no PDF download required) when Unpaywall finds no open-access PDF.

    Rate limit: 10 req/sec with a free API key — no practical constraint for our use.
    Authentication: Bearer token in the Authorization header. Calls are skipped when
    core_api_key is not configured.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.core_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": self.settings.metadata_user_agent}
        if self.settings.core_api_key:
            headers["Authorization"] = f"Bearer {self.settings.core_api_key}"
        return headers

    def _parse_core_work(self, item: dict[str, Any]) -> tuple[str | None, list[str], int | None, str | None]:
        """Extract (doi, authors, year, abstract) from a CORE work object."""
        doi_raw = str(item.get("doi") or "").lower().strip()
        for prefix in ("https://doi.org/", "http://doi.org/"):
            if doi_raw.startswith(prefix):
                doi_raw = doi_raw[len(prefix):]
        doi = doi_raw or None

        authors: list[str] = [
            str(a.get("name", "")).strip()
            for a in (item.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]

        year_raw = item.get("yearPublished")
        try:
            year: int | None = int(year_raw) if year_raw is not None else None
        except (TypeError, ValueError):
            year = None

        abstract: str | None = item.get("abstract") or None
        return doi, authors, year, abstract

    def search_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> MetadataLookupResponse:
        """Search CORE for a paper by title, applying the same three false-match
        gates as the other title-search clients (title exact/substring, year ±1,
        first-author last name).

        Called only when CrossRef, OpenAlex, and SemanticScholar all fail to resolve
        a title to a DOI. CORE's coverage of institutional repositories makes it
        particularly useful for management and social-science papers that are available
        as accepted manuscripts but not formally indexed elsewhere.
        """
        params: dict[str, str] = {"q": title.strip(), "limit": "5"}
        url = f"{self.base_url}/search/works"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    response = client.get(url, headers=self._headers(), params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_LOOKUP_TIMEOUT", error_message=str(exc))
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="METADATA_SERVICE_UNAVAILABLE", error_message=str(exc))

        if response.status_code != 200:
            return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.LOOKUP_FAILED.value, status_code=response.status_code, error_code="DOI_LOOKUP_FAILED", error_message=f"CORE search returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.LOOKUP_FAILED.value, error_code="DOI_LOOKUP_FAILED", error_message=f"Malformed JSON from CORE: {exc}")

        results = payload.get("results") or []
        if not results:
            return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="METADATA_UNAVAILABLE", error_message="CORE title search returned no results.")

        for item in results:
            result_title = str(item.get("title") or "")
            if not _title_matches(title, result_title):
                continue
            found_doi, result_authors, result_year, abstract = self._parse_core_work(item)
            if year is not None and result_year is not None and abs(year - result_year) > 1:
                continue
            if authors and result_authors and not _first_author_matches(authors, result_authors):
                continue
            # All gates passed
            download_url: str | None = item.get("downloadUrl") or None
            url_field = (f"https://doi.org/{found_doi}" if found_doi else download_url)
            return MetadataLookupResponse(
                success=True,
                lookup_source="CORE-TitleSearch",
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                doi=found_doi,
                title=result_title or None,
                authors=result_authors or None,
                year=result_year,
                venue=None,
                publisher=None,
                abstract=abstract,
                url=url_field,
                raw_metadata_json=item,
                status_code=response.status_code,
            )

        return MetadataLookupResponse(success=False, lookup_source="CORE", lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, error_code="TITLE_MATCH_INSUFFICIENT", error_message=f"No CORE result passed title/author/year gates for query '{title[:80]}'.")

    def get_fulltext_by_doi(self, doi: str) -> tuple[str | None, str | None]:
        """Return (full_text, source_label) for a paper by DOI using the CORE API.

        CORE returns the full text directly in the JSON response for many papers,
        avoiding the need to download and parse a PDF. The source label is either
        the CORE download URL (when full text comes from a downloadable file) or a
        synthetic 'core:{doi}' string (when text is returned inline).

        Returns (None, None) on any failure so the caller can fall back gracefully.
        """
        # Search by DOI using the quoted doi: qualifier understood by CORE's search engine
        params: dict[str, str] = {"q": f'doi:"{doi}"', "limit": "1"}
        url = f"{self.base_url}/search/works"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    response = client.get(url, headers=self._headers(), params=params)
        except Exception:
            return None, None

        if response.status_code != 200:
            return None, None

        try:
            payload = response.json()
        except Exception:
            return None, None

        results = payload.get("results") or []
        if not results:
            return None, None

        item = results[0]
        full_text: str | None = item.get("fullText") or None
        if full_text and isinstance(full_text, str):
            full_text = full_text.strip()[:self.settings.fulltext_max_chars] or None
        download_url: str | None = item.get("downloadUrl") or None
        if not download_url:
            # sourceFulltextUrls is a list of direct PDF/HTML links from data providers
            source_urls = item.get("sourceFulltextUrls") or []
            if isinstance(source_urls, list) and source_urls:
                download_url = source_urls[0] or None

        if full_text:
            return full_text, download_url or f"core:{doi}"
        # No inline full text — return the download URL so the caller can try PDF extraction
        return None, download_url


class SsrnClient:
    """SSRN preprint client — fetches the abstract for SSRN working papers.

    SSRN (Social Science Research Network) hosts working papers for management,
    economics, law, and social science. Papers carry DOIs of the form
    10.2139/ssrn.XXXXXXX and are indexed by CrossRef, but CrossRef rarely
    includes the abstract. This client fetches it directly from the SSRN paper
    page using a regex over the HTML.

    Full PDFs require a free SSRN account, so we retrieve abstracts only.
    Evidence packages for SSRN papers are classified as PREPRINT_AVAILABLE (not
    FULL_TEXT_AVAILABLE or ABSTRACT_AVAILABLE) to signal that the text comes
    from a working paper, not the final peer-reviewed publication.
    """

    _SSRN_DOI_RE = re.compile(r"^10\.2139/ssrn\.(\d+)$", re.IGNORECASE)
    _ABSTRACT_PAGE = "https://papers.ssrn.com/sol3/papers.cfm"

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    @classmethod
    def ssrn_id_from_doi(cls, doi: str) -> str | None:
        """Return the numeric SSRN paper ID from a 10.2139/ssrn.XXXXXXX DOI, or None."""
        m = cls._SSRN_DOI_RE.match(doi.strip())
        return m.group(1) if m else None

    def get_abstract_for_doi(self, doi: str) -> str | None:
        """Return the abstract text for an SSRN paper identified by its DOI, or None."""
        ssrn_id = self.ssrn_id_from_doi(doi)
        if not ssrn_id:
            return None
        return self._fetch_abstract(ssrn_id)

    def _fetch_abstract(self, ssrn_id: str) -> str | None:
        headers = {
            "User-Agent": self.settings.metadata_user_agent,
            "Accept": "text/html",
        }
        params = {"abstract_id": ssrn_id}
        try:
            if self._client is not None:
                response = self._client.get(self._ABSTRACT_PAGE, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    response = client.get(self._ABSTRACT_PAGE, headers=headers, params=params)
        except Exception:
            return None

        if response.status_code != 200:
            return None

        page_text = response.text
        # Primary: SSRN renders the abstract inside <div class="abstract-text">
        match = re.search(r'<div[^>]+class="abstract-text[^"]*"[^>]*>(.*?)</div>', page_text, re.DOTALL | re.IGNORECASE)
        if not match:
            # Fallback: schema.org description attribute
            match = re.search(r'itemprop=["\']description["\'][^>]*>(.*?)</(?:div|span|p)>', page_text, re.DOTALL | re.IGNORECASE)
        if not match:
            return None

        raw = match.group(1)
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None


def _reconstruct_openalex_abstract(inverted_index: Any) -> str | None:
    """Reconstruct plain text from OpenAlex's inverted-index abstract format."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None
    position_word: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                if isinstance(pos, int):
                    position_word[pos] = word
    if not position_word:
        return None
    return " ".join(position_word[i] for i in sorted(position_word)).strip() or None


class PubMedClient:
    """NCBI PubMed E-utilities client for abstract retrieval.

    PubMed has strong coverage of psychology, medicine, neuroscience, and life
    sciences — domains where CrossRef and OpenAlex often lack abstracts. Uses
    the free E-utilities API (no key required, polite-pool email recommended).

    Two calls per lookup: esearch (DOI → PMID) then efetch (PMID → abstract XML).
    Called only when all other abstract providers returned nothing.
    """

    _BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def _params(self, extra: dict[str, str]) -> dict[str, str]:
        """Build E-utilities params, adding the polite-pool email when available."""
        p: dict[str, str] = {"tool": "verifai", **extra}
        if self.settings.crossref_mailto:
            p["email"] = self.settings.crossref_mailto
        return p

    def _get(self, endpoint: str, params: dict[str, str]) -> httpx.Response | None:
        url = f"{self._BASE}/{endpoint}"
        try:
            if self._client is not None:
                return self._client.get(url, params=params, timeout=self.timeout)
            with httpx.Client(timeout=self.timeout) as client:
                return client.get(url, params=params)
        except httpx.HTTPError:
            return None

    def lookup_by_doi(self, doi: str) -> MetadataLookupResponse:
        """Return abstract and metadata for a paper identified by DOI.

        Step 1: esearch — translate DOI to PubMed ID (PMID).
        Step 2: efetch — retrieve the PubMed XML record and parse abstract,
                title, authors, and year.

        Returns success=False when PubMed has no record for the DOI, or when
        the record exists but has no abstract (common for older articles).
        """
        r = self._get("esearch.fcgi", self._params({
            "db": "pubmed", "term": f"{doi}[doi]", "retmode": "json", "retmax": "1",
        }))
        if r is None or r.status_code != 200:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi,
                error_code="METADATA_SERVICE_UNAVAILABLE",
                error_message="PubMed esearch request failed.",
            )

        try:
            search_payload = r.json()
        except ValueError:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi,
                error_code="DOI_LOOKUP_FAILED", error_message="PubMed esearch returned malformed JSON.",
            )

        pmid_list = (search_payload.get("esearchresult") or {}).get("idlist") or []
        if not pmid_list:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, doi=doi,
                error_code="METADATA_UNAVAILABLE",
                error_message="PubMed found no record for this DOI.",
            )

        pmid = str(pmid_list[0])

        r2 = self._get("efetch.fcgi", self._params({
            "db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "xml",
        }))
        if r2 is None or r2.status_code != 200:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi,
                error_code="DOI_LOOKUP_FAILED", error_message="PubMed efetch request failed.",
            )

        try:
            root = ET.fromstring(r2.text)
        except ET.ParseError:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value, doi=doi,
                error_code="DOI_LOOKUP_FAILED", error_message="PubMed returned malformed XML.",
            )

        # AbstractText may be split into structured sections (Background, Methods, …)
        abstract_parts = [el.text for el in root.iter("AbstractText") if el.text]
        abstract = " ".join(abstract_parts).strip() or None

        if not abstract:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value, doi=doi,
                error_code="METADATA_UNAVAILABLE",
                error_message="PubMed record exists but has no abstract.",
            )

        title_el = root.find(".//ArticleTitle")
        title = (title_el.text or "").strip() or None

        authors: list[str] = []
        for author_el in root.iter("Author"):
            last = author_el.findtext("LastName") or ""
            fore = author_el.findtext("ForeName") or author_el.findtext("Initials") or ""
            name = f"{fore} {last}".strip() if fore else last.strip()
            if name:
                authors.append(name)

        year: int | None = None
        pub_date = root.find(".//PubDate")
        if pub_date is not None:
            try:
                year = int(pub_date.findtext("Year") or "")
            except ValueError:
                pass

        return MetadataLookupResponse(
            success=True,
            lookup_source="PubMed",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=doi,
            title=title,
            authors=authors or None,
            year=year,
            abstract=abstract,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            raw_metadata_json={"pmid": pmid},
            status_code=r2.status_code,
        )

    def search_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> MetadataLookupResponse:
        """Search PubMed by title and return the best confident match with its DOI.

        Uses the same three false-match gates as the other title-search clients:
        title exact/substring match, year ±1, first-author last name.

        Step 1: esearch with [Title] field tag → up to 5 PMIDs.
        Step 2: esummary (batch) → structured JSON with DOI, authors, pubdate.

        PubMed rate limit: < 3 req/sec with tool+email params (polite pool) —
        no practical constraint for our volume.
        """
        query = f"{title.strip()}[Title]"
        r = self._get("esearch.fcgi", self._params({
            "db": "pubmed", "term": query, "retmode": "json", "retmax": "5",
        }))
        if r is None or r.status_code != 200:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="METADATA_SERVICE_UNAVAILABLE",
                error_message="PubMed esearch request failed.",
            )

        try:
            search_payload = r.json()
        except ValueError:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="DOI_LOOKUP_FAILED",
                error_message="PubMed esearch returned malformed JSON.",
            )

        pmids = (search_payload.get("esearchresult") or {}).get("idlist") or []
        if not pmids:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="METADATA_UNAVAILABLE",
                error_message=f"PubMed title search returned no results for '{title[:80]}'.",
            )

        r2 = self._get("esummary.fcgi", self._params({
            "db": "pubmed", "id": ",".join(pmids[:5]), "retmode": "json",
        }))
        if r2 is None or r2.status_code != 200:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="DOI_LOOKUP_FAILED",
                error_message="PubMed esummary request failed.",
            )

        try:
            summary = r2.json()
        except ValueError:
            return MetadataLookupResponse(
                success=False, lookup_source="PubMed",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="DOI_LOOKUP_FAILED",
                error_message="PubMed esummary returned malformed JSON.",
            )

        result_map = summary.get("result") or {}
        for pmid in (result_map.get("uids") or pmids):
            item = result_map.get(str(pmid)) or {}

            result_title = str(item.get("title") or "")
            if not _title_matches(title, result_title):
                continue

            pubdate = str(item.get("pubdate") or "")
            year_match = re.match(r"\d{4}", pubdate)
            result_year: int | None = int(year_match.group()) if year_match else None
            if year is not None and result_year is not None and abs(year - result_year) > 1:
                continue

            result_authors = [
                str(a.get("name", "")).strip()
                for a in (item.get("authors") or [])
                if isinstance(a, dict) and a.get("name")
            ]
            if authors and result_authors and not _first_author_matches(authors, result_authors):
                continue

            found_doi: str | None = None
            for aid in (item.get("articleids") or []):
                if isinstance(aid, dict) and aid.get("idtype") == "doi":
                    found_doi = str(aid.get("value") or "").strip() or None
                    break

            return MetadataLookupResponse(
                success=True,
                lookup_source="PubMed-TitleSearch",
                lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
                doi=found_doi,
                title=result_title or None,
                authors=result_authors or None,
                year=result_year,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                raw_metadata_json=item,
                status_code=r2.status_code,
            )

        return MetadataLookupResponse(
            success=False, lookup_source="PubMed",
            lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
            error_code="TITLE_MATCH_INSUFFICIENT",
            error_message=f"No PubMed result passed title/author/year gates for query '{title[:80]}'.",
        )


class GoogleBooksClient:
    """Google Books API client for ISBN resolution of textbooks.

    Textbooks are frequently cited in academic papers without a DOI — they
    have ISBNs instead. Google Books has near-complete coverage of published
    books and returns ISBN-13, which can then be fed to CrossRef's ISBN filter
    to obtain the registered DOI (if one exists).

    The API is free up to 1,000 req/day without a key, and 10,000 req/day with
    a free GOOGLE_BOOKS_API_KEY. The key is optional — the client works without it.
    """

    _BASE = "https://www.googleapis.com/books/v1"

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def find_isbn_by_title(
        self,
        title: str,
        authors: str | None = None,
        year: int | None = None,
    ) -> str | None:
        """Search Google Books by title and return the ISBN-13 (or ISBN-10) of the best match.

        Applies the same false-match gates as all other title-search clients:
        title exact/substring match, year ±1, first-author last name.

        Returns the ISBN string (digits only, no hyphens) or None on any failure.
        The caller is expected to pipe the ISBN to CrossrefClient.lookup_by_isbn()
        to resolve it into a DOI.
        """
        params: dict[str, str] = {
            "q": f"intitle:{title.strip()}",
            "maxResults": "5",
            "printType": "books",
        }
        if self.settings.google_books_api_key:
            params["key"] = self.settings.google_books_api_key

        url = f"{self._BASE}/volumes"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, params=params)
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        for item in (payload.get("items") or []):
            volume = item.get("volumeInfo") or {}
            result_title = str(volume.get("title") or "")
            if not _title_matches(title, result_title):
                continue

            pub_date = str(volume.get("publishedDate") or "")
            year_match = re.match(r"\d{4}", pub_date)
            result_year: int | None = int(year_match.group()) if year_match else None
            if year is not None and result_year is not None and abs(year - result_year) > 1:
                continue

            result_authors = [str(a) for a in (volume.get("authors") or []) if a]
            if authors and result_authors and not _first_author_matches(authors, result_authors):
                continue

            # Prefer ISBN-13, fall back to ISBN-10
            for preferred_type in ("ISBN_13", "ISBN_10"):
                for identifier in (volume.get("industryIdentifiers") or []):
                    if isinstance(identifier, dict) and identifier.get("type") == preferred_type:
                        raw = str(identifier.get("identifier") or "")
                        isbn = re.sub(r"[-\s]", "", raw)
                        if isbn:
                            return isbn

        return None


class DoiResolverClient:
    """Minimal DOI resolver URL helper.

    BE-5 uses this only as a safe URL fallback. It does not scrape publisher pages.
    """

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.doi_resolver_base_url.rstrip("/")

    def resolver_url(self, doi: str) -> str:
        return f"{self.base_url}/{doi}"
