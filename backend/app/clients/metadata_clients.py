from __future__ import annotations

import difflib
import re
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
    """Lowercase, strip punctuation, collapse whitespace for fuzzy comparison."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _title_similarity(a: str, b: str) -> float:
    """Combined [0, 1] similarity score for two titles.

    Uses the maximum of:
    - Character-level SequenceMatcher ratio (handles typos and reorderings)
    - Word-level coverage ratio (what fraction of the shorter title's words appear
      in the longer title) — only applied when the shorter title has >= 6 words to
      prevent false positives on very short titles

    This makes the score robust to the common case where an extracted title is
    the paper title without subtitle, which SequenceMatcher alone scores ~0.78-0.80.
    """
    if not a or not b:
        return 0.0
    na, nb = _normalize_title(a), _normalize_title(b)
    char_ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    words_a = set(na.split())
    words_b = set(nb.split())
    shorter = words_a if len(words_a) <= len(words_b) else words_b
    longer = words_b if shorter is words_a else words_a
    if len(shorter) >= 6:
        word_coverage = len(shorter & longer) / len(shorter)
        return max(char_ratio, word_coverage)
    return char_ratio


def _authors_overlap(reference_authors_str: str, result_authors: list[str]) -> bool:
    """Return True if at least one last name from the reference appears in the result."""
    def last_names(text: str) -> set[str]:
        names: set[str] = set()
        for part in re.split(r"[;,]", text):
            tokens = part.strip().split()
            if tokens:
                names.add(tokens[-1].lower())
        return names

    ref_last = last_names(reference_authors_str)
    result_last: set[str] = set()
    for name in result_authors:
        tokens = name.strip().split()
        if tokens:
            result_last.add(tokens[-1].lower())
    return bool(ref_last & result_last)


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
        *,
        min_title_similarity: float = 0.95,
    ) -> MetadataLookupResponse:
        """Search Semantic Scholar for a paper by title and return the best confident match.

        False-match prevention (all checks must pass):
        - Title similarity ≥ min_title_similarity (required gate, fuzzy normalized match)
        - Year must match within 1 year when both reference and result have a year
        - At least one author last name must overlap when both sides have authors

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

        if response.status_code != 200:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"Semantic Scholar search returned HTTP {response.status_code}.",
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

        # Gate 1 — title similarity (primary false-match guard)
        similarity = _title_similarity(title, result_title)
        if similarity < min_title_similarity:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="TITLE_MATCH_INSUFFICIENT",
                error_message=(
                    f"Best match '{result_title}' had title similarity {similarity:.2f}, "
                    f"below threshold {min_title_similarity}."
                ),
            )

        # Gate 2 — year match (reject on hard mismatch, skip if either side has no year)
        result_year: int | None = best.get("year")
        if year is not None and result_year is not None and abs(year - result_year) > 1:
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="YEAR_MISMATCH",
                error_message=f"Year mismatch: reference={year}, found={result_year}.",
            )

        # Gate 3 — author overlap (reject if both sides have authors but no last-name overlap)
        result_authors_raw: list[str] = [
            str(a.get("name", "")).strip()
            for a in (best.get("authors") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        if authors and result_authors_raw and not _authors_overlap(authors, result_authors_raw):
            return MetadataLookupResponse(
                success=False,
                lookup_source="SemanticScholar",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                error_code="AUTHOR_MISMATCH",
                error_message="No author last-name overlap between reference and search result.",
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


class DoiResolverClient:
    """Minimal DOI resolver URL helper.

    BE-5 uses this only as a safe URL fallback. It does not scrape publisher pages.
    """

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.doi_resolver_base_url.rstrip("/")

    def resolver_url(self, doi: str) -> str:
        return f"{self.base_url}/{doi}"
